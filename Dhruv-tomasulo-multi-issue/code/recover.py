# recover.py
# Recovery after a misprediction (or after a load read a wrong value).
# Everything younger than the last instruction we keep is thrown away:
#   1. the ROB entries, reservation stations, functional units, load/store
#      queue and results waiting for the CDB lose these instructions
#      (this also clears the wait-for tags of the wrong instructions)
#   2. the RAT is built again from the instructions that are left in the ROB
# This takes one cycle. If the problem is found in cycle n, the correct
# instruction is fetched (and issued) in cycle n + 2.


def squash(m, keep_seq, resume_pc, cycle):
    victims = [e for e in m.rob if e.seq > keep_seq]
    for e in victims:
        e.squashed = True
    m.n_squashed += len(victims)

    m.rob = type(m.rob)(e for e in m.rob if not e.squashed)
    for k in m.rs:
        m.rs[k] = [e for e in m.rs[k] if not e.squashed]
    for k in m.in_ex:
        m.in_ex[k] = [e for e in m.in_ex[k] if not e.squashed]
    m.addr_unit = [e for e in m.addr_unit if not e.squashed]
    m.lsq = [e for e in m.lsq if not e.squashed]
    m.results = [r for r in m.results if not r[0].squashed]
    m.port_users = [u for u in m.port_users if not u.squashed]

    m.rat = {}
    for e in m.rob:
        if e.dest is not None:
            m.rat[e.dest] = e

    m.pc = resume_pc
    m.issue_block = cycle + 2
