"""Requested-output pipeline: evidence extraction, optional review, selective writing."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

from .analysis import OLLAMA, OllamaClient, chunk_segments, safe_text
from .core import atomic_json, clock, fingerprint
from .report_profiles import (
    PROFILES,
    PROMPT_VERSION,
    VERIFY_PROMPT,
    VERIFY_SCHEMA,
    WITHDRAWAL_PROMPT,
    WITHDRAWAL_SCHEMA,
    build_prompt,
    schema_for,
)


class ReportClient(OllamaClient):
    def complete(self, model, system, content, schema):
        qwen3 = model.lower().startswith("qwen3:")
        # Qwen3's documented non-thinking sampling is intentional; JSON schema
        # and source checks constrain the extraction, not a promise of determinism.
        options = {
            "num_ctx": 8192,
            "num_predict": 4096,
            "seed": 42,
            "temperature": 0.7 if qwen3 else 0.15,
            "top_p": 0.8 if qwen3 else 0.9,
            "top_k": 20 if qwen3 else 40,
            "min_p": 0,
        }
        payload = {
            "model": model,
            "stream": True,
            "think": False,
            "keep_alive": "5m",
            "format": schema,
            "options": options,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        }
        req = urllib.request.Request(
            OLLAMA + "/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
        )
        done, pieces = False, []
        try:
            with self.opener.open(req, timeout=900) as response:
                for line in response:
                    part = json.loads(line)
                    if part.get("error"):
                        raise RuntimeError(str(part["error"]))
                    pieces.append(part.get("message", {}).get("content", ""))
                    if part.get("done"):
                        done = True
                        if part.get("done_reason") == "length":
                            raise RuntimeError(
                                "OUTPUT_LIMIT: Die Modellantwort wurde abgeschnitten."
                            )
            if not done:
                raise RuntimeError("Ollama hat die Antwort unvollständig beendet.")
            return json.loads("".join(pieces))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                "Ollama: " + exc.read(2000).decode("utf-8", "replace")
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("INVALID_JSON: " + str(exc)) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeError("Lokales Ollama nicht erreichbar: " + str(exc)) from exc


def validate_items(raw, kind, segments, aliases):
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise ValueError(
            "Die Modellausgabe entspricht nicht der angeforderten Auswertung."
        )
    by_id = {s["id"]: s for s in segments}
    result, notes = [], []
    for item in raw["items"]:
        if (
            not isinstance(item, dict)
            or item.get("category") not in PROFILES[kind]["categories"]
            or not isinstance(item.get("text"), str)
            or not item["text"].strip()
        ):
            notes.append(
                "Ein Eintrag mit falschem Typ oder ohne Inhalt wurde ausgelassen."
            )
            continue
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            notes.append("Eine Aussage ohne Quellenbeleg wurde ausgelassen.")
            continue
        valid = all(
            isinstance(e, dict)
            and isinstance(e.get("quote"), str)
            and bool(e["quote"].strip())
            and e.get("segment") in by_id
            and e["quote"] in by_id[e["segment"]]["text"]
            for e in evidence
        )
        if not valid:
            notes.append(
                "Eine Aussage mit nicht wörtlich belegbaren Quellen wurde ausgelassen."
            )
            continue
        entry = copy.deepcopy(item)
        entry["heading"] = str(entry.get("heading") or "Gesprächsinhalt")
        entry["sources"] = list(dict.fromkeys(e["segment"] for e in evidence))
        entry["said_by"] = list(
            dict.fromkeys(by_id[e["segment"]]["speaker"] for e in evidence)
        )
        if kind == "tasks":
            if entry.get("status") not in (
                "zugesagt",
                "beauftragt",
                "angefragt",
                "offen",
                "zurückgenommen",
            ):
                entry["status"] = "offen"
            original = "\n".join(by_id[e["segment"]]["text"] for e in evidence)
            owner, owner_quote = (
                str(entry.get("owner") or ""),
                str(entry.get("owner_evidence") or ""),
            )
            self_name = any(
                owner in (speaker, aliases.get(speaker, speaker))
                for speaker in entry["said_by"]
            )
            self_reference = bool(
                re.search(r"\b(ich|meine[nmrs]?|mir|i|my)\b", owner_quote, re.I)
            )
            if owner and not (
                owner_quote
                and owner_quote in original
                and (
                    owner.casefold() in owner_quote.casefold()
                    or (self_name and self_reference)
                )
            ):
                entry["owner"] = ""
                notes.append("Eine nicht belegbare Zuständigkeit bleibt offen.")
            due, due_quote = (
                str(entry.get("due") or ""),
                str(entry.get("due_evidence") or ""),
            )
            if due and not (
                due_quote
                and due_quote in original
                and due.casefold() in due_quote.casefold()
            ):
                entry["due"] = ""
                notes.append("Ein nicht ausdrücklich belegbarer Termin wurde entfernt.")
        if kind == "decisions" and entry.get("status") not in (
            "angenommen",
            "abgelehnt",
            "vertagt",
            "zurückgenommen",
            "nicht genannt",
        ):
            entry["status"] = "nicht genannt"
        result.append(entry)
    return result, notes


def verify_items(client, model, items, segments):
    if not items:
        return [], []
    source_ids = {x for item in items for x in item["sources"]}
    draft = [{"id": f"i{i}", **item} for i, item in enumerate(items)]
    source = [
        {"id": s["id"], "speaker": s["speaker"], "text": s["text"]}
        for s in segments
        if s["id"] in source_ids
    ]
    content = json.dumps({"drafts": draft, "transcript": source}, ensure_ascii=False)
    if len(content) > 9000 and len(items) > 1:
        middle = len(items) // 2
        a, na = verify_items(client, model, items[:middle], segments)
        b, nb = verify_items(client, model, items[middle:], segments)
        return a + b, na + nb
    if len(content) > 9000:
        for s in source:
            ranges = []
            for e in items[0]["evidence"]:
                if e["segment"] == s["id"]:
                    pos = s["text"].find(e["quote"])
                    ranges.append(
                        s["text"][max(0, pos - 200) : pos + len(e["quote"]) + 200]
                    )
            s["text"] = " […] ".join(ranges)
        content = json.dumps(
            {"drafts": draft, "transcript_excerpts": source}, ensure_ascii=False
        )
    raw = client.complete(model, VERIFY_PROMPT, content, VERIFY_SCHEMA)
    approved, rejected = raw.get("approved"), raw.get("rejected")
    if not isinstance(approved, list) or not isinstance(rejected, list):
        raise ValueError("Die Belegprüfung lieferte kein vollständiges Prüfergebnis.")
    valid_ids = {x["id"] for x in draft}
    rejected_ids = {x.get("id") for x in rejected if isinstance(x, dict)}
    if (
        not all(isinstance(x, str) for x in approved)
        or len(approved) + len(rejected) != len(valid_ids)
        or set(approved) & rejected_ids
        or set(approved) | rejected_ids != valid_ids
    ):
        raise ValueError(
            "Die Belegprüfung hat nicht jeden Eintrag eindeutig geprüft. Bitte erneut starten."
        )
    notes = [
        "Belegprüfung: " + str(x.get("reason") or "Nicht ausreichend belegt")
        for x in rejected
    ]
    return [item for i, item in enumerate(items) if f"i{i}" in approved], notes


def support_segments(chunk, project):
    merged = []
    for segment in chunk:
        if merged and merged[-1]["id"] == segment["id"]:
            merged[-1]["text"] += segment["text"]
        else:
            merged.append(dict(segment))
    positions = {s["id"]: i for i, s in enumerate(project["segments"])}
    first, last = positions[merged[0]["id"]], positions[merged[-1]["id"]]
    before = [
        {**s, "text": s["text"][-400:]}
        for s in project["segments"][max(0, first - 2) : first]
    ]
    after = [
        {**s, "text": s["text"][:400]} for s in project["segments"][last + 1 : last + 3]
    ]
    return before + merged + after


def extract_part(client, model, kind, options, chunk, project, depth=0):
    support = support_segments(chunk, project)
    core_ids = {s["id"] for s in chunk}
    payload = {
        "context": {
            "title": project.get("title", ""),
            "date": project.get("date", ""),
            "agenda": project.get("context", "")[:1800],
        },
        "speakers": project.get("speakers", {}),
        "core_segment_ids": list(core_ids),
        "transcript": [
            {
                "id": s["id"],
                "role": "core" if s["id"] in core_ids else "context",
                "speaker": s["speaker"],
                "start": clock(s["start"]),
                "text": s["text"],
            }
            for s in support
        ],
    }
    try:
        return client.complete(
            model,
            build_prompt(kind, options),
            json.dumps(payload, ensure_ascii=False),
            schema_for(kind),
        )
    except RuntimeError as exc:
        if depth >= 3 or not any(
            x in str(exc) for x in ("OUTPUT_LIMIT", "INVALID_JSON")
        ):
            raise
        if len(chunk) > 1:
            half = len(chunk) // 2
            groups = [chunk[:half], chunk[half:]]
        elif len(chunk[0]["text"]) > 650:
            segment = chunk[0]
            half = len(segment["text"]) // 2
            groups = [
                [{**segment, "text": segment["text"][:half]}],
                [{**segment, "text": segment["text"][half:]}],
            ]
        else:
            raise
        return {
            "items": [
                item
                for group in groups
                for item in extract_part(
                    client, model, kind, options, group, project, depth + 1
                )["items"]
            ]
        }


def compact_summary(client, model, items, options, segments, progress, notes):
    """Hierarchical reduction retains evidence and represents the complete meeting."""
    current = items
    for level in range(8):
        groups, group, size = [], [], 0
        for item in current:
            length = len(json.dumps(item, ensure_ascii=False))
            if group and size + length > 6000:
                groups.append(group)
                group, size = [], 0
            group.append(item)
            size += length
        if group:
            groups.append(group)
        if not groups:
            return []
        finished = len(groups) == 1
        reduced = []
        for index, group in enumerate(groups):
            progress(
                "phase",
                {
                    "text": f"Gesamtzusammenfassung · Verdichtung {level + 1}, Teil {index + 1}/{len(groups)}"
                },
            )
            limit = (
                min(8, max(1, len(group) // 2))
                if not finished
                else (5 if options.get("detail") == "short" else 8)
            )
            prompt = (
                build_prompt("summary", options, "reduce")
                + f"\nErzeuge höchstens {limit} Einträge und insgesamt höchstens 1500 Zeichen Text."
            )
            raw = client.complete(
                model,
                prompt,
                json.dumps({"verified_items": group}, ensure_ascii=False),
                schema_for("summary"),
            )
            clean, warnings = validate_items(raw, "summary", segments, {})
            notes.extend(warnings)
            if not clean and group:
                raise ValueError(
                    "Die Gesamtzusammenfassung hat keine gültigen Belege geliefert."
                )
            if len(clean) > limit:
                raise ValueError(
                    "Das Modell hat die gewünschte Kürze nicht eingehalten. Bitte erneut versuchen."
                )
            reduced.extend(clean)
        if finished:
            return reduced
        if len(reduced) >= len(current) and level > 1:
            raise ValueError(
                "Das Modell verdichtet die Zwischenstände nicht ausreichend. Ein anderes Modell wählen."
            )
        current = reduced
    raise ValueError(
        "Die Zusammenfassung konnte nicht innerhalb des Kontextbudgets verdichtet werden."
    )


def reconcile_withdrawals(client, model, items, segments, progress):
    """Only explicit, later withdrawals can suppress an earlier task; never mere similarity."""
    by_id = {s["id"]: s for s in segments}
    result = copy.deepcopy(items)
    suppressed = set()
    notes = []
    for index, current in enumerate(result):
        if current.get("status") != "zurückgenommen" or not current.get("owner"):
            continue
        when = max(by_id[s]["start"] for s in current["sources"])
        candidates = [
            (i, previous)
            for i, previous in enumerate(result)
            if i != index
            and i not in suppressed
            and previous.get("status") not in ("zurückgenommen", "offen")
            and previous.get("owner") == current["owner"]
            and max(by_id[s]["start"] for s in previous["sources"]) < when
        ]
        if not candidates:
            continue
        progress(
            "phase", {"text": "Zurückgenommene Zusagen über die Sitzung abgleichen …"}
        )
        # Small batches keep a late withdrawal comparable with even an early assignment.
        old_texts = []
        for start in range(0, len(candidates), 4):
            group = candidates[start : start + 4]
            raw = client.complete(
                model,
                WITHDRAWAL_PROMPT,
                json.dumps(
                    {
                        "withdrawal": current,
                        "earlier_tasks": [{"id": f"i{i}", **item} for i, item in group],
                    },
                    ensure_ascii=False,
                ),
                WITHDRAWAL_SCHEMA,
            )
            ids = raw.get("superseded")
            allowed = {f"i{i}": (i, item) for i, item in group}
            if not isinstance(ids, list) or any(
                not isinstance(x, str) or x not in allowed for x in ids
            ):
                raise ValueError(
                    "Der Rücknahmeabgleich hat keine gültigen Aufgabenzuordnungen geliefert."
                )
            for ident in dict.fromkeys(ids):
                old_index, old = allowed[ident]
                suppressed.add(old_index)
                old_texts.append(old["text"])
                for evidence in old["evidence"]:
                    if evidence not in current["evidence"]:
                        current["evidence"].append(evidence)
                current["sources"] = list(
                    dict.fromkeys(current["sources"] + old["sources"])
                )
                current.setdefault("withdrawal_of", []).append(old["text"])
        if old_texts:
            current["text"] = "; ".join(old_texts)
            current["due"] = ""
            notes.append(
                "Eine frühere Zusage wurde aufgrund einer später ausdrücklich belegten Rücknahme als zurückgenommen ausgewiesen."
            )
    return [item for i, item in enumerate(result) if i not in suppressed], notes


def render_markdown(project, model, kind, items, notes, options):
    aliases, by_id = (
        project.get("speakers", {}),
        {s["id"]: s for s in project["segments"]},
    )
    label = PROFILES[kind]["label"]
    english = options.get("language") == "en"
    if english:
        label = {
            "minutes": "Detailed minutes",
            "results": "Results and open points",
            "chronological": "Chronological minutes",
            "summary": "Summary",
            "tasks": "Action items",
            "decisions": "Decisions and votes",
            "interview": "Interview analysis",
        }[kind]
    lines = [
        f"# {safe_text(project.get('title') or label)}",
        "",
        f"## {label}",
        "",
        f"{'Date' if english else 'Datum'}: {safe_text(project.get('date', ''))}  ",
        f"{'Model' if english else 'Modell'}: {safe_text(model)}  ",
        f"{'Prompt version' if english else 'Promptversion'}: {PROMPT_VERSION}",
        "",
        "> "
        + (
            "AI draft · Timestamps refer to the edited recording."
            if english
            else "KI-Entwurf · Zeitmarken beziehen sich auf die bearbeitete Audiofassung."
        ),
        "",
    ]
    if project.get("preliminary"):
        lines += [
            "> "
            + (
                "Based on a preliminary live transcript."
                if english
                else "Grundlage ist ein vorläufiges Live-Transkript."
            ),
            "",
        ]

    def refs(item):
        return " · ".join(
            f"[{clock(by_id[s]['start'])} · {safe_text(aliases.get(by_id[s]['speaker'], by_id[s]['speaker']))}](#{s})"
            for s in item["sources"]
        )

    if not items:
        empty = (
            "Keine ausdrücklich belegbaren Aufgaben gefunden."
            if kind == "tasks"
            else "Keine ausdrücklich belegten Beschlüsse oder Abstimmungen gefunden."
            if kind == "decisions"
            else "Für diese Auswertung wurden keine ausreichend belegbaren Inhalte gefunden."
        )
        lines += [
            (
                "No sufficiently evidenced items were found for this request."
                if english
                else empty
            ),
            "",
        ]
    if kind == "tasks":
        items = sorted(items, key=lambda item: item.get("status") == "zurückgenommen")
        withdrawal_heading = False
        for item in items:
            if item.get("status") == "zurückgenommen" and not withdrawal_heading:
                lines += [
                    "### "
                    + (
                        "Withdrawn commitments"
                        if english
                        else "Zurückgenommene Zusagen"
                    ),
                    "",
                ]
                withdrawal_heading = True
            who = ", ".join(aliases.get(x, x) for x in item["said_by"])
            prefix = "- " if item.get("status") == "zurückgenommen" else "- [ ] "
            status = item.get("status", "offen")
            if english:
                status = {
                    "zugesagt": "committed",
                    "beauftragt": "assigned",
                    "angefragt": "requested",
                    "offen": "open",
                    "zurückgenommen": "withdrawn",
                }.get(status, status)
            lines += [
                f"{prefix}**{safe_text(item['text'])}**",
                f"  - Status: {safe_text(status)}",
                f"  - {'Owner / requested person' if english else 'Zuständig / angefragt'}: {safe_text(item.get('owner') or ('Open' if english else 'Offen'))}",
                f"  - {'Mentioned by' if english else 'Erwähnt von'}: {safe_text(who)}",
                f"  - {'Due date (as stated)' if english else 'Termin (wie genannt)'}: {safe_text(item.get('due') or ('Not stated' if english else 'Nicht genannt'))}",
                "  - " + refs(item),
                "",
            ]
    elif kind == "summary":
        for item in items:
            lines += ["- " + safe_text(item["text"]) + " " + refs(item), ""]
    else:
        last_heading = None
        for item in items:
            heading = item["heading"]
            if kind == "chronological":
                heading = clock(by_id[item["sources"][0]]["start"]) + " · " + heading
            if heading != last_heading:
                lines += ["### " + safe_text(heading), ""]
                last_heading = heading
            lines += [safe_text(item["text"]), ""]
            if kind == "decisions":
                lines += [
                    "Status: " + safe_text(item.get("status", "nicht genannt")),
                    "",
                ]
            lines += [refs(item), ""]
    if notes:
        lines += (
            ["## " + ("Review notes" if english else "Prüfhinweise"), ""]
            + ["- " + safe_text(n) for n in dict.fromkeys(notes)]
            + [""]
        )
    if options.get("include_sources", True):
        lines += ["## " + ("Sources" if english else "Fundstellen"), ""]
        ids = {x for item in items for x in item["sources"]}
        for s in project["segments"]:
            if s["id"] in ids:
                lines += [
                    f"### {s['id']}",
                    "",
                    f"**{clock(s['start'])}–{clock(s['end'])} · {safe_text(aliases.get(s['speaker'], s['speaker']))}**",
                    "",
                    safe_text(s["text"]),
                    "",
                ]
    return "\n".join(lines)


def read_checkpoint(path, kind, project):
    """A cache accelerates work; an interrupted/corrupt cache must never block it."""
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(stored, dict)
            or not isinstance(stored.get("items"), list)
            or not isinstance(stored.get("notes"), list)
        ):
            return None
        if any(not isinstance(note, str) for note in stored["notes"]):
            return None
        clean, warnings = validate_items(
            stored, kind, project["segments"], project.get("speakers", {})
        )
        if warnings or clean != stored["items"]:
            return None
        return stored
    except (OSError, ValueError, TypeError, KeyError):
        return None


def generate_report(
    project, model, kind, options=None, progress=lambda *args: None, client=None
):
    if kind not in PROFILES:
        raise ValueError("Bitte eine gültige Auswertungsart auswählen.")
    options = {
        "language": "de",
        "detail": "detailed",
        "focus": "",
        "verify": True,
        "include_sources": True,
        **(options or {}),
    }
    client = client or ReportClient()
    client.check_model(model)
    chunks = chunk_segments(
        project.get("segments", []), max_chars=3800, max_seconds=240
    )
    if not chunks:
        raise ValueError("Bitte zuerst ein Transkript erstellen oder importieren.")
    contract = hashlib.sha256(
        json.dumps(
            [
                PROMPT_VERSION,
                build_prompt(kind, options),
                schema_for(kind),
                VERIFY_PROMPT,
                VERIFY_SCHEMA,
                WITHDRAWAL_PROMPT,
            ],
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    key_data = [fingerprint(project), model, kind, options, contract]
    cache = (
        Path(project["directory"])
        / "report-cache"
        / hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    )
    cache.mkdir(parents=True, exist_ok=True)
    items, notes = [], []
    for index, chunk in enumerate(chunks):
        progress(
            "progress",
            {"current": index + 1, "total": len(chunks), "model": model, "kind": kind},
        )
        checkpoint = cache / f"{index:04d}.json"
        stored = read_checkpoint(checkpoint, kind, project)
        if stored is not None:
            clean, warnings = stored["items"], stored["notes"]
        else:
            raw = extract_part(client, model, kind, options, chunk, project)
            support = support_segments(chunk, project)
            clean, warnings = validate_items(
                raw, kind, support, project.get("speakers", {})
            )
            if raw["items"] and not clean and warnings:
                raise ValueError(
                    "Das Modell hat für diesen Abschnitt keine gültig belegte Auswertung geliefert. Bitte erneut starten oder ein anderes Modell wählen."
                )
            core_ids = {s["id"] for s in chunk}
            clean = [item for item in clean if core_ids.intersection(item["sources"])]
            if options["verify"] and clean:
                progress(
                    "phase",
                    {"text": f"Belege prüfen · Abschnitt {index + 1}/{len(chunks)}"},
                )
                clean, review_notes = verify_items(client, model, clean, support)
                warnings.extend(review_notes)
            atomic_json(checkpoint, {"items": clean, "notes": warnings})
        items.extend(clean)
        notes.extend(warnings)
    if kind == "summary" and items:
        final_path = cache / "summary.json"
        stored = read_checkpoint(final_path, kind, project)
        if stored is not None:
            items = stored["items"]
            notes.extend(stored.get("notes", []))
        else:
            note_start = len(notes)
            items = compact_summary(
                client, model, items, options, project["segments"], progress, notes
            )
            if options["verify"]:
                items, warnings = verify_items(
                    client, model, items, project["segments"]
                )
                notes.extend(warnings)
            atomic_json(final_path, {"items": items, "notes": notes[note_start:]})
    if kind == "tasks" and any(
        item.get("status") == "zurückgenommen" for item in items
    ):
        final_path = cache / "withdrawals.json"
        stored = read_checkpoint(final_path, kind, project)
        if stored is not None:
            items = stored["items"]
            notes.extend(stored["notes"])
        else:
            items, withdrawal_notes = reconcile_withdrawals(
                client, model, items, project["segments"], progress
            )
            notes.extend(withdrawal_notes)
            atomic_json(final_path, {"items": items, "notes": withdrawal_notes})
    # Only exact repeats are deduplicated. Different states or conflicting claims remain visible.
    seen, unique = set(), []
    for item in items:
        signature = (
            item["text"].casefold().strip(),
            item.get("owner", ""),
            item.get("due", ""),
            item.get("status", ""),
        )
        if signature not in seen:
            seen.add(signature)
            unique.append(item)
    if kind == "chronological":
        source_times = {s["id"]: s["start"] for s in project["segments"]}
        unique.sort(key=lambda item: min(source_times[s] for s in item["sources"]))
    return {
        "kind": kind,
        "label": PROFILES[kind]["label"],
        "model": model,
        "options": options,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": contract,
        "fingerprint": fingerprint(project),
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "markdown": render_markdown(project, model, kind, unique, notes, options),
        "items": unique,
        "tasks": unique if kind == "tasks" else [],
        "sources": project["segments"],
        "speakers": project.get("speakers", {}),
        "warnings": list(dict.fromkeys(notes)),
        "chunks": len(chunks),
    }
