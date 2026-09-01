# Roadmap

> **Done (1 Sept 2026).** Needs Attention, Watch List, Stayed In Range with a
> selectable window (24h / 7d / 30d / 90d), an excursion history per device, and a
> readable fleet temperature chart. Revert point: `git tag pre-ui-overhaul`.
> Items 3–10 remain open; 1 and 2 are covered below.


Candidate changes, ranked. Effort estimates assume the existing stack; nothing
here requires new infrastructure.

Categories:
- **Parity** — SmartSense has it and we don't. Closing a gap someone will notice.
- **Advantage** — something they cannot easily do, given their architecture.
- **Later** — real, but not before a pilot has run.

See `docs/competitor-analysis.md` for the evidence behind each.

---

## 1 · Incident tracking — MOSTLY DONE

**Done.** The **Excursions** panel on Device Detail lists every excursion: when it
started, how long it lasted, how far past the limit it went at worst, and how many
readings it covers. Warm and cold are coloured differently, and duration is banded
by colour on the same <1h / 1–3h / >3h boundaries SmartSense uses.

It is computed from `telemetry` with window functions rather than written to an
`incidents` table by a watcher. That was the better trade: **it works on history
that already exists**, so the panel was populated the moment it was added instead
of starting empty and filling up over the following weeks. It also cannot drift
out of sync with the readings, and it re-scores correctly if a limit is corrected.

**Still open:** acknowledgement and corrective-action notes (items 4 and 5) do
need somewhere to write, so they will need a table keyed on device + start time.
The severity banding SmartSense reports is display-only and already covered.

*Previously recorded as the gap:*

SmartSense records start time, **duration**, severity banded as Short (<1h) /
Medium (1–3h) / Long (>3h), and **max / min / average** reading per incident.

**Why it matters.** Food safety is time *and* temperature. Ten minutes at 40 °F is
a door being opened; four hours is a written-off load. Without duration we cannot
tell those apart, and neither can an auditor.

**Shape.** An `incidents` table written by a small watcher: device, started_at,
ended_at, peak reading, average, duration. Then a panel listing recent incidents
and a per-incident view.

---

## 2 · Percent time in range — DONE

**Done.** **Stayed In Range** scores every unit against its own company's limits,
sorted worst-first, with a **Compliance window** dropdown at the top of the
dashboard offering 24 hours / 7 days / 30 days / 90 days. The fleet-wide figure
sits beside it and follows the same window.

The dropdown is deliberately separate from the dashboard time picker: the picker
defaults to 6 hours because that is the right span for watching temperatures move,
and it is a useless span for a compliance figure. Tying them together would have
made one of the two wrong.

*Previously recorded as the gap:* Their Asset Health report scores every asset by the share of time it
spent inside its limits, which is how they surfaced that Plymouth Phoenix 3 sits
at 54%.

**Why it matters.** It is the single number a customer or auditor asks for, and
it turns "we send alerts" into "here is the state of your cold chain."

**Shape.** One query over `telemetry` joined to `devices`, grouped by month. A stat
panel per device and a fleet table. Straightforward once incidents exist, and
useful even before.

---

## 3 · Email alerts alongside Slack — PARITY — ~1 hour

**The gap.** They notify by email, SMS and phone; we do Slack only. Their incident
log shows emails going to named recipients at plymouthinc.com and nickyusa.com.

**Why it matters.** Not everyone is in Slack, and "does it email me?" is an easy
objection to remove.

**Shape.** Grafana supports email contact points natively — SMTP settings on the
grafana service, then a second contact point. SMS would need Twilio and is not
worth it yet.

---

## 4 · Acknowledge and assign — PARITY, with a caveat — ~half a day

**The gap.** No way to mark an alert as being dealt with, or to say who owns it.

**The caveat.** Their manual acknowledgement is exactly what left 15 resolved
incidents sitting on their dashboard. **Copy the assignment, keep our auto-resolve.**
An acknowledged incident should still close itself when the temperature recovers.

---

## 5 · Corrective action logging — PARITY — ~half a day

**The gap.** When an excursion happens, nothing records what was done about it.

**Why it matters.** This is the HACCP-relevant piece: an auditor asks not only
"did it go out of range" but "what did you do." Pairs naturally with incidents.

**Shape.** A note attached to an incident — who responded, what they found, what
action was taken, timestamp.

---

## 6 · Audit log for threshold changes — ADVANTAGE — ~2–3 hours

**The gap.** Nothing records who changed a temperature limit, or what it was
before.

**Why it matters.** If a ceiling quietly moves from 34 °F to 45 °F and product
spoils, there is currently no way to find out who did it or when. In a compliance
system that is a real hole — and one their Alarm Configuration Report suggests
they also have, since it shows *what* is configured but not *who changed it*.

**Shape.** A `device_changes` table written by the admin UI: user, field, old
value, new value, timestamp. Plus a recent-activity page.

---

## 7 · Data export — PARITY — ~1 hour

**The gap.** Their asset view has a download button; ours has none.

**Why it matters.** Auditors and insurers ask for raw data. Grafana's table panels
support CSV export out of the box — it may only need enabling and testing.

---

## 8 · User management in the UI — LATER — ~1–2 hours

Adding a person or restricting them to one company currently needs SQL. The
scoping works; there is simply no screen for it. Necessary the moment a second
person needs access.

---

## 9 · Asset layer — LATER — ~half a day

Separating *the sensor* from *the thing being monitored*, so a freezer keeps
continuous history across hardware replacements while every reading still names
the sensor that took it.

**Not before a pilot.** It shows nothing until a sensor has been replaced, it
touches the core data model, and after one real replacement we will know how it
actually behaves rather than guessing.

---

## 10 · Humidity — LATER

Some of their assets monitor humidity as well as temperature. Our payload and
schema are temperature-only. Worth knowing if any Plymouth asset depends on it;
adding a column and a sensor is not difficult, but nothing calls for it yet.

---

## Explicitly not doing

**Digital checklists / task management.** SmartSense sells this (Jolt), but
Plymouth's account does not have it — their navigation is Dashboard, Assets,
Gateways, Reports, Incidents, Admin. Building an operations platform is a
different product.

**Mobile app.** The dashboard is responsive and reachable on a phone over the
network. A native app solves nothing we have.

**Predictive analytics.** Their marketing claims it; their screens show a
"prescriptive action" column with three canned strings. Not worth chasing.

---

## Suggested order

1 and 2 together — they share a query and produce the compliance report that is
currently the clearest thing SmartSense has and we do not. Then 3, since it is an
hour and removes an objection. Then 6, because it protects against a failure that
is silent and expensive. The rest after a pilot.
