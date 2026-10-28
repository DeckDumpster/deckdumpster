import subprocess, sys, tempfile, sqlite3, pathlib, re
sys.path.insert(0, "tests")
import pyarrow as pa
from mtg_collector.lake import iceberg_prices as lake
import test_lake_valuation as t
DAYS, ROWS = 40, 200_000
tmp = pathlib.Path(tempfile.mkdtemp()); wh = tmp/"wh"; wh.mkdir()
cat = lake.open_catalog(str(tmp/"cat.sqlite"), f"file://{wh}")
table, _ = lake.ensure_tables(cat)
ids = range(ROWS)
for d in range(DAYS):
    table.append(pa.Table.from_pydict({
        "uuid": ["u%d-%d" % (d, i) for i in ids], "set_code": ["s%d" % (i % 900) for i in ids],
        "collector_number": ["%d" % (i % 400) for i in ids], "source": ["tcgplayer"] * ROWS,
        "price_type": ["normal"] * ROWS, "price_cents": [i % 5000 for i in ids],
        "observed_date": ["2026-%02d-%02d" % (1 + d // 28, 1 + d % 28)] * ROWS}, schema=table.schema().as_arrow()))
shared = tmp/"shared.sqlite"; sqlite3.connect(shared).close()
for label, patch in (("NEW", ""), ("OLD", "from mtg_collector.lake import valuation as v\nv._file_batches=lambda t,c: t.scan(selected_fields=c).to_arrow_batch_reader()\n")):
    code = patch + t._PEAK_PROBE
    out = subprocess.run([sys.executable, "-c", code, str(shared), str(tmp/"cat.sqlite"), f"file://{wh}", str(DAYS*ROWS)], capture_output=True, text=True, timeout=900)
    print("PROBE", label, out.stdout.strip().splitlines()[-1:] , out.stderr[-300:], flush=True)
