# clinic-mockdb

Records service for the patient portal. Serves patient records over HTTP to
`clinic-backend`. Node stdlib only — no dependencies, no build step.

This is the non-production records shim used in clinic environments that are not
wired to the central records system. Sites on central records do not run it.

## Endpoints

| Method | Path | Returns |
|---|---|---|
| `GET` | `/healthz` | `{"status":"ok","service":"clinic-mockdb"}` |
| `GET` | `/patients` | `{"count":N,"patients":[…]}` |
| `GET` | `/patients?q=<term>` | Same, filtered on name or MRN, case-insensitive substring |

Unknown paths return `404 {"error":"not_found"}`.
An unreadable or malformed data file returns `500 {"error":"datafile_unreadable"}`
and writes the parse error to stderr.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `MOCKDB_PORT` | `5432` | Listen port |
| `MOCKDB_BIND` | `0.0.0.0` | Listen address |
| `MOCKDB_DATA` | `./patients.json` | Path to the records file |

## Running

```bash
MOCKDB_PORT=5432 node server.js
```

Under systemd the unit is `clinic-mockdb`; `clinic-backend` reaches it via its
own `DB_HOST` and `DB_PORT` settings.

## Data file

`patients.json` holds a `patients` array. Each record:

```json
{
  "mrn": "MRN-004182",
  "name": "Avery Lindqvist",
  "dob": "1971-03-14",
  "status": "active",
  "provider": "Okonkwo, D.",
  "lastVisit": "2026-07-19",
  "flags": ["allergy:penicillin"]
}
```

`flags` is a free-form string array rendered as chips in the portal.
`status` is `active` or `inactive`.

**All records in this file are fabricated test data.** No real person, MRN, or
clinical event is represented. Do not add live records to this file — sites
handling live records must run against central records, not this service.

The file is re-read on every request, so edits take effect without a restart.
Malformed JSON takes the service to a 500 on the next request rather than at
write time, so validate before saving:

```bash
node -e "JSON.parse(require('fs').readFileSync('patients.json'))" && echo ok
```
