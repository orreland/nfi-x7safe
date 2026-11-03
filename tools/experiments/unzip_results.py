"""Extract freqtrade result zips in stopgrid-* dirs so eval_grid._result_json() finds the json."""
import glob
import os
import sys
import zipfile

base = r"D:\NostalgiaForInfinity\user_data\backtest_results"
for d in sys.argv[1:]:
    for z in glob.glob(os.path.join(base, d, "backtest-result-*.zip")):
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if not os.path.exists(os.path.join(base, d, n)):
                    zf.extract(n, os.path.join(base, d))
        print(d, sorted(os.listdir(os.path.join(base, d))))
