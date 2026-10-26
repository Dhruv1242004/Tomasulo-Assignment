# Runs every t*.txt file at issue width 1..4, checks it, and saves the output.
import glob, io, os, sys, contextlib
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
sys.path.insert(0, os.path.join(here, '..', 'code'))
from check import check
from main import run
from print_status import print_report

os.makedirs(os.path.join(here, 'results'), exist_ok=True)
bad = 0
rows = []
for f in sorted(glob.glob(os.path.join(here, 't*.txt'))):
    name = os.path.basename(f)[:-4]
    text = open(f).read()
    cycles = []
    for w in (1, 2, 3, 4):
        problems, m = check(text, w)
        if problems:
            bad += 1
            print(name, 'width', w, 'PROBLEMS:', problems[:3])
        cycles.append(m.last_commit_cycle)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_report(m)
        open(os.path.join(here, 'results', '%s_w%d.txt' % (name, w)), 'w').write(buf.getvalue())
    rows.append((name, cycles))
print('%-26s %5s %5s %5s %5s' % ('test', 'w=1', 'w=2', 'w=3', 'w=4'))
for name, c in rows:
    print('%-26s %5d %5d %5d %5d' % ((name,) + tuple(c)))
print('all checks passed' if bad == 0 else '%d runs had problems' % bad)
