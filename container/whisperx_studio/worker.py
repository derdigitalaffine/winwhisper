"""Subprocess boundary makes model loading/generation immediately cancellable."""
import argparse
import json
from pathlib import Path
import sys

from .analysis import generate, OllamaClient
from .core import atomic_json


def emit(kind, data):
    print(json.dumps({"type": kind, "data": data}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("models", nargs="+")
    args = parser.parse_args()
    project = json.loads(args.project.read_text(encoding="utf-8"))
    client = OllamaClient()
    request = project.get("requested_report")
    if request:
        from .reports import ReportClient, generate_report
        client = ReportClient()
    for index, model in enumerate(args.models):
        try:
            if request:
                report = generate_report(project, model, request["kind"], request.get("options"), emit, client=client)
            else:
                report = generate(project, model, project["directory"], emit, client=client)
        finally:
            try:
                client.unload(model)
            except Exception:
                pass
        output = args.project.parent / f"report-{index}.json"
        atomic_json(output, report)
        emit("report", str(output))
    emit("finished", "Auswertung fertig")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit("error", str(exc))
        sys.exit(1)
