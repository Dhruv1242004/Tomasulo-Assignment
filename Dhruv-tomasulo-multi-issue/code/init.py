# init.py
# Data types for the simulator and the reader for the input file.
#
# The input file has (in any order):
#   - the hardware table (rs, EX cycles, memory cycles, number of units)
#   - "ROB entries = N", "Issue width = N"
#   - register values:   R1=10, F2=30.1
#   - memory values:     Mem[4]=1, Mem[8]=2.5
#   - the program, one instruction per line
# Text is not case sensitive. "//" and "#" start a comment.

import re
from collections import deque


class SimError(Exception):
    """Something is wrong with the input or the program."""
    pass


# ---------------------------------------------------------------------
# hardware configuration (defaults are the values the starter main.py used)
# ---------------------------------------------------------------------
class Config:
    def __init__(self):
        self.int_rs, self.int_ex, self.int_units = 4, 1, 1
        self.fpadd_rs, self.fpadd_ex, self.fpadd_units = 3, 4, 1
        self.fpmul_rs, self.fpmul_ex, self.fpmul_units = 2, 15, 1
        self.ls_rs, self.ls_ex, self.ls_mem, self.ls_units = 5, 1, 5, 1
        self.rob_size = 64
        self.issue_width = 1
        self.commit_width = None     # None means: same as issue width
        self.cdb_width = 1           # results that can be broadcast per cycle
        self.load_speculation = True # loads may pass stores with unknown address
        self.regs = {}               # 'R1' -> 10, 'F2' -> 30.1
        self.mem = {}                # byte address -> value (like the starter, every
                                     # byte address 0..255 holds one value)


# ---------------------------------------------------------------------
# one instruction of the program
# ---------------------------------------------------------------------
class Instr:
    def __init__(self, op, text):
        self.op = op          # Ld Sd Beq Bne Add Addi Sub Add.d Sub.d Mult.d
        self.text = text      # printable form, e.g. "Ld F4, 8(R1)"
        self.kind = None      # 'int', 'fpadd', 'fpmul', 'ld', 'sd', 'br'
        self.dest = None      # register that is written ('R3', 'F1') or None
        self.src1 = None      # first register read   (for Sd: the data register)
        self.src2 = None      # second register read
        self.base = None      # base register of Ld / Sd
        self.imm = 0          # immediate, load/store offset, or branch offset


KIND = {'Add': 'int', 'Addi': 'int', 'Sub': 'int',
        'Add.d': 'fpadd', 'Sub.d': 'fpadd', 'Mult.d': 'fpmul',
        'Ld': 'ld', 'Sd': 'sd', 'Beq': 'br', 'Bne': 'br'}
OPNAME = dict((k.lower(), k) for k in KIND)


def _reg(tok, kind, line_no):
    m = re.match(r'^([rf])(\d+)$', tok.lower())
    if not m or int(m.group(2)) > 31 or m.group(1).upper() != kind:
        raise SimError("line %d: '%s' is not a valid %s register" %
                       (line_no, tok, 'integer (R0-R31)' if kind == 'R' else 'floating point (F0-F31)'))
    return kind + str(int(m.group(2)))


def _int(tok, line_no):
    try:
        return int(tok)
    except ValueError:
        raise SimError("line %d: '%s' is not an integer" % (line_no, tok))


def parse_instruction(line, line_no):
    toks = line.replace(',', ' ').split()
    op = OPNAME.get(toks[0].lower())
    if op is None:
        raise SimError("line %d: unknown instruction '%s'" % (line_no, toks[0]))
    args = toks[1:]
    ins = Instr(op, '')
    ins.kind = KIND[op]

    def need(n):
        if len(args) != n:
            raise SimError("line %d: %s needs %d operands" % (line_no, op, n))

    if op in ('Add', 'Sub'):
        need(3)
        ins.dest = _reg(args[0], 'R', line_no)
        ins.src1 = _reg(args[1], 'R', line_no)
        ins.src2 = _reg(args[2], 'R', line_no)
        ins.text = '%s %s, %s, %s' % (op, ins.dest, ins.src1, ins.src2)
    elif op == 'Addi':
        need(3)
        ins.dest = _reg(args[0], 'R', line_no)
        ins.src1 = _reg(args[1], 'R', line_no)
        ins.imm = _int(args[2], line_no)
        ins.text = '%s %s, %s, %d' % (op, ins.dest, ins.src1, ins.imm)
    elif op in ('Add.d', 'Sub.d', 'Mult.d'):
        need(3)
        ins.dest = _reg(args[0], 'F', line_no)
        ins.src1 = _reg(args[1], 'F', line_no)
        ins.src2 = _reg(args[2], 'F', line_no)
        ins.text = '%s %s, %s, %s' % (op, ins.dest, ins.src1, ins.src2)
    elif op in ('Ld', 'Sd'):
        need(2)
        reg = _reg(args[0], 'F', line_no)
        m = re.match(r'^(-?\d+)\((\w+)\)$', args[1])
        if not m:
            raise SimError("line %d: expected offset(Rn), found '%s'" % (line_no, args[1]))
        ins.imm = int(m.group(1))
        ins.base = _reg(m.group(2), 'R', line_no)
        if op == 'Ld':
            ins.dest = reg
        else:
            ins.src1 = reg          # the value to store
        ins.text = '%s %s, %d(%s)' % (op, reg, ins.imm, ins.base)
    else:                            # Beq, Bne
        need(3)
        ins.src1 = _reg(args[0], 'R', line_no)
        ins.src2 = _reg(args[1], 'R', line_no)
        ins.imm = _int(args[2], line_no)
        ins.text = '%s %s, %s, %d' % (op, ins.src1, ins.src2, ins.imm)
    if ins.dest == 'R0':
        ins.dest = None              # R0 is always 0, a write to it is dropped
    return ins


def _number(tok, line_no):
    try:
        return int(tok)
    except ValueError:
        try:
            return float(tok)
        except ValueError:
            raise SimError("line %d: '%s' is not a number" % (line_no, tok))


def read_input(text, issue_width=None):
    """Turn the text of an input file into (Config, [Instr])."""
    cfg = Config()
    program = []
    units = {'integer adder': 'int', 'fp adder': 'fpadd',
             'fp multiplier': 'fpmul', 'load/store unit': 'ls'}

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = re.split(r'//|#', raw)[0].strip()
        if not line:
            continue
        low = line.lower()

        # hardware table: label followed by numbers
        label = next((u for u in units if low.startswith(u)), None)
        if label:
            nums = [_int(t, line_no) for t in line[len(label):].split()]
            k = units[label]
            if k == 'ls':
                if len(nums) != 4:
                    raise SimError("line %d: load/store unit needs 4 numbers (rs, ex, mem, units)" % line_no)
                cfg.ls_rs, cfg.ls_ex, cfg.ls_mem, cfg.ls_units = nums
            else:
                if len(nums) == 4:           # an unused memory column was filled in
                    nums = [nums[0], nums[1], nums[3]]
                if len(nums) != 3:
                    raise SimError("line %d: %s needs 3 numbers (rs, ex, units)" % (line_no, label))
                setattr(cfg, k + '_rs', nums[0])
                setattr(cfg, k + '_ex', nums[1])
                setattr(cfg, k + '_units', nums[2])
            continue

        # single settings
        m = re.match(r'^(rob entries|issue width|commit width|cdb width|load speculation)\s*=\s*(\S+)$', low)
        if m:
            name, val = m.group(1), m.group(2)
            if name == 'load speculation':
                if val not in ('on', 'off'):
                    raise SimError("line %d: load speculation must be on or off" % line_no)
                cfg.load_speculation = (val == 'on')
            else:
                n = _int(val, line_no)
                if n < 1:
                    raise SimError("line %d: %s must be at least 1" % (line_no, name))
                if name == 'rob entries':
                    cfg.rob_size = n
                elif name == 'issue width':
                    cfg.issue_width = n
                elif name == 'commit width':
                    cfg.commit_width = n
                else:
                    cfg.cdb_width = n
            continue

        # register and memory values
        if '=' in line and re.match(r'^(r|f|mem\s*\[)', low):
            for item in line.split(','):
                item = item.strip()
                if not item:
                    continue
                m = re.match(r'^([rfRF]\d+|mem\s*\[\s*\d+\s*\])\s*=\s*(\S+)$', item, re.I)
                if not m:
                    raise SimError("line %d: cannot read '%s'" % (line_no, item))
                name, val = m.group(1), _number(m.group(2), line_no)
                if name[0] in 'mM':
                    addr = int(re.search(r'\d+', name).group())
                    if addr > 255:
                        raise SimError("line %d: memory address %d is outside the 256 byte memory" % (line_no, addr))
                    cfg.mem[addr] = val
                else:
                    reg = name[0].upper() + str(int(name[1:]))
                    if int(name[1:]) > 31:
                        raise SimError("line %d: no register %s" % (line_no, name))
                    if reg == 'R0' and val != 0:
                        raise SimError("line %d: R0 is always 0" % line_no)
                    cfg.regs[reg] = val
            continue

        program.append(parse_instruction(line, line_no))

    if issue_width is not None:
        cfg.issue_width = issue_width
    if not 1 <= cfg.issue_width <= 4:
        raise SimError("issue width must be between 1 and 4")
    if cfg.commit_width is None:
        cfg.commit_width = cfg.issue_width
    if not program:
        raise SimError("the input has no instructions")
    return cfg, program


# ---------------------------------------------------------------------
# run time records
# ---------------------------------------------------------------------
class Operand:
    """One source value of an instruction: either known, or waiting for a ROB entry."""
    def __init__(self, value=None, avail=0, producer=None):
        self.value = value        # the value, once known
        self.avail = avail        # first cycle in which the value can be used
        self.producer = producer  # ROB entry that will broadcast it (None if known)

    def ready(self, cycle):
        return self.producer is None and self.avail <= cycle


class ROBEntry:
    def __init__(self, seq, tag, pc, ins, issue):
        self.seq = seq            # number of the instruction in fetch order
        self.tag = tag            # ROB0, ROB1, ...
        self.pc = pc              # index of the instruction in the program
        self.ins = ins
        self.dest = ins.dest
        self.issue = issue
        self.ex_start = self.ex_end = None
        self.mem_start = self.mem_end = None
        self.wb = None
        self.commit = None
        self.value = None
        self.squashed = False
        self.ops = []             # Operand objects
        # branches
        self.pred_taken = False
        self.pred_next = None
        self.taken = None
        self.mispredicted = False
        # loads and stores
        self.address = None
        self.addr_visible = None  # first cycle the address can be used
        self.fwd_from = None      # seq of the store a load got its value from (-1: memory)
        self.in_lsq = False


class Machine:
    """All state of the processor."""
    def __init__(self, cfg, program):
        self.cfg = cfg
        self.program = program
        self.cycle = 0
        self.pc = 0                       # next instruction to fetch
        self.issue_block = 0              # no issue before this cycle (recovery)
        self.seq = 0
        # architectural state
        self.regs = {}
        for i in range(32):
            self.regs['R%d' % i] = 0
            self.regs['F%d' % i] = 0
        self.regs.update(cfg.regs)
        self.memory = dict(cfg.mem)       # only non-default words are stored
        # structures
        self.rob = deque()
        self.rat = {}                     # register -> ROBEntry that will write it
        self.rs = {'int': [], 'fpadd': [], 'fpmul': []}
        self.rs_size = {'int': cfg.int_rs, 'fpadd': cfg.fpadd_rs, 'fpmul': cfg.fpmul_rs}
        self.ex_time = {'int': cfg.int_ex, 'fpadd': cfg.fpadd_ex, 'fpmul': cfg.fpmul_ex}
        self.units = {'int': cfg.int_units, 'fpadd': cfg.fpadd_units, 'fpmul': cfg.fpmul_units}
        self.pipelined = {'int': False, 'fpadd': True, 'fpmul': True}
        self.in_ex = {'int': [], 'fpadd': [], 'fpmul': []}   # entries running in a unit
        self.lsq = []                     # loads and stores in program order
        self.addr_unit = []               # loads/stores computing their address
        self.port_users = []              # loads reading memory and stores writing it
        self.results = []                 # finished results waiting for the CDB
        self.btb = [None] * 8             # (pc, target, taken bit)
        # output
        self.done_rows = []               # committed entries, in commit order
        self.events = []                  # text lines: mispredictions etc.
        self.n_branches = 0
        self.n_mispredicts = 0
        self.n_violations = 0
        self.n_squashed = 0
        self.last_commit_cycle = 0
