# TASK DEPMAP - a dependency map that answers "who breaks if I retire this"

## Why this exists

Twice a session retired something a page still depended on (analysis.html,
check_symbol). Both survived review because interactive paths appear in no log
and no schedule - nothing reads them until a human opens the page. Prose cannot
be checked before a change. A generated index can.

## Deliverables

1. `_tools/depmap.py` - the generator. Static analysis only: parse Python with
   `ast`, read everything else as text. It must NOT import project modules, must
   not open the database for writing, must not call the network, must not touch
   the service.
2. `_tools/dependency_map.json` - machine readable, regenerated on every run.
3. `_tools/DEPENDENCY_MAP.md` - human readable, produced by the same run. Its
   header carries the generation time, the commit sha, and the counts below.
4. A query mode:
   `python3 _tools/depmap.py --who-consumes THING`
   where THING is a file path, an endpoint path, a table name, or a Python
   symbol. It prints every consumer and exits 1 when it finds none.
   When the answer is empty it must distinguish "nothing consumes this" from
   "this scanner does not cover that kind of thing". An empty answer that reads
   as confident is the exact failure this task exists to prevent.

## Edges to extract, each with file and line number

- Python import edges, module to module, via `ast`.
- FastAPI routes: method, path, handler function, file.
- Pages under `www/trading/` and any JS they load: which endpoint paths they
  request.
- Home Assistant `configuration.yaml`: rest and command_line sensors and the
  URLs they poll. Locate that file first - do not assume its path.
- SQL per file: tables read (FROM, JOIN) and tables written (INSERT INTO,
  UPDATE, CREATE TABLE, DELETE FROM), tagged read or write.
- Schedules: APScheduler jobs, cron entries for the pi user, systemd timers, and
  the function each one drives.
- Shell entry points in `_tools/` that call Python or the service.

## The reverse index is the point of the task

For every endpoint, every table, and every Python function referenced from
outside its own file, list every consumer. Sort the report so that things with
zero consumers form their own section. That section is the retire-safely list,
and it is also where a blind spot in the scanner will show up first.

## Accuracy rules

- Never guess. A request URL built at runtime from a variable is recorded as
  `dynamic` with its file and line, in its own section. Do not drop it.
- Count what you scanned: how many Python files, HTML files, YAML files. Name
  the directories you excluded and why.
- If a directory is too large or too noisy to scan, say so in the report rather
  than skipping it silently.

## Verify before you finish

- Run the generator twice. The JSON must be byte-identical the second time.
- `--who-consumes www/trading/analysis.html` and `--who-consumes check_symbol`
  must both return something sensible. Those are the two known breakages.
- `--who-consumes /dashboard/radar` must list the Home Assistant sensor and the
  pages that read it.
- Time the run and put the number in the report.

## Out of scope

- No edits to `server.py`, `dashboard_api.py`, or any runtime module. The tree
  carries in-flight work from a parallel session. Leave every file you did not
  create alone.
- No database writes, no restart, no schema change, no network calls.
- If something here turns out to be wrong about the codebase, stop and write
  that in the report instead of widening the work.

## Commit

Stage by name: `_tools/depmap.py`, `_tools/dependency_map.json`,
`_tools/DEPENDENCY_MAP.md`. Nothing else. Blanket staging is blocked by a hook.
