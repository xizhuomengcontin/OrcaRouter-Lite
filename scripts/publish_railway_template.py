#!/usr/bin/env python
"""Publish the Railway template and wire its code into the Deploy buttons.

Railway only serves a real one-click deploy for a *published template code*:
`https://railway.com/new/template/<code>`. A URL without one — including the
legacy `?template=<github-url>` form the READMEs used to carry — lands the
visitor on the generic marketplace page and deploys nothing.

Template codes cannot be minted from a repo URL; `templateGenerate` snapshots an
existing Railway project (its services, variables and volumes). So the flow is:

    1. Deploy this repo on Railway once, by hand:
         railway.com -> New Project -> Deploy from GitHub repo -> OrcaRouter-Lite
       Add the `/data` volume and the variables listed at the top of
       railway.toml. Whatever that project looks like is what deployers get.

    2. Grab an account token: https://railway.com/account/tokens

    3. Run this script. It snapshots the project, publishes it, and rewrites the
       Railway row in all twelve READMEs to point at the resulting code.

Usage
-----
    export RAILWAY_TOKEN=...

    # find the project you deployed in step 1
    python scripts/publish_railway_template.py --list-projects

    # snapshot + publish it, then update the READMEs
    python scripts/publish_railway_template.py --project-id <id> --write-readmes

    # already published from the dashboard? just wire up the buttons:
    python scripts/publish_railway_template.py --code ZweBXA --write-readmes

Add --dry-run to any of these to see what would change without writing.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

API = "https://backboard.railway.com/graphql/v2"
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

BUTTON = (
    "[![Deploy on Railway](https://railway.com/button.svg)]"
    "(https://railway.com/new/template/{code}"
    "?utm_medium=integration&utm_source=button&utm_campaign=orcarouter-lite)"
)

DEFAULT_DESCRIPTION = (
    "Self-hosted, OpenAI-compatible LLM router. BYOK, cross-provider failover, "
    "model=\"auto\" cost routing, prompt cache and a built-in dashboard."
)

DEFAULT_README = """\
# OrcaRouter Lite

Self-hosted LLM router with a managed safety net — OpenAI-compatible, BYOK,
single-workspace.

After deploying, open the service URL for the dashboard and add provider keys
there, or set them as variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...).

The `/data` volume holds the SQLite database — provider keys, API keys and
analytics. Do not remove it.

Source: https://github.com/Continuum-AI-Corp/OrcaRouter-Lite
"""


class RailwayError(RuntimeError):
    pass


def gql(token: str, query: str, variables: dict | None = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:  # 401 etc — surface the body, not a traceback
        detail = e.read().decode(errors="replace")[:500]
        raise RailwayError(f"HTTP {e.code} from Railway: {detail}") from None
    except urllib.error.URLError as e:
        raise RailwayError(f"could not reach {API}: {e.reason}") from None

    if payload.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in payload["errors"])
        raise RailwayError(msgs)
    return payload["data"]


# ── Railway calls ──────────────────────────────────────────────────────

def list_projects(token: str) -> None:
    data = gql(
        token,
        """
        query { projects(first: 50) { edges { node {
            id name
            environments(first: 10) { edges { node { id name } } }
        } } } }
        """,
    )
    edges = data["projects"]["edges"]
    if not edges:
        print("No projects on this account. Deploy the repo on Railway first "
              "(New Project -> Deploy from GitHub repo).")
        return
    for e in edges:
        p = e["node"]
        print(f"{p['id']}  {p['name']}")
        for ee in p["environments"]["edges"]:
            env = ee["node"]
            print(f"    env  {env['id']}  {env['name']}")


def generate_and_publish(
    token: str, project_id: str, environment_id: str | None, category: str
) -> str:
    existing = gql(
        token,
        "query($p: String!) { templateSourceForProject(projectId: $p) { id code } }",
        {"p": project_id},
    )["templateSourceForProject"]
    if existing and existing.get("code"):
        print(f"project already has template {existing['id']} (code {existing['code']}) "
              f"— republishing it")
        template_id = existing["id"]
    else:
        payload = {"projectId": project_id}
        if environment_id:
            payload["environmentId"] = environment_id
        template = gql(
            token,
            "mutation($i: TemplateGenerateInput!) { templateGenerate(input: $i) { id code } }",
            {"i": payload},
        )["templateGenerate"]
        template_id = template["id"]
        print(f"snapshotted project into template {template_id}")

    published = gql(
        token,
        """
        mutation($id: String!, $i: TemplatePublishInput!) {
          templatePublish(id: $id, input: $i) { code isApproved }
        }
        """,
        {
            "id": template_id,
            "i": {
                "category": category,
                "description": DEFAULT_DESCRIPTION,
                "readme": DEFAULT_README,
            },
        },
    )["templatePublish"]

    code = published["code"]
    if not published.get("isApproved"):
        print("note: Railway lists the template only after it approves it; the "
              "deploy link works immediately either way.")
    return code


# ── README rewriting ───────────────────────────────────────────────────

RAILWAY_ROW = re.compile(r"^\| Railway \| .* \|\s*$")


def write_readmes(code: str, dry_run: bool) -> int:
    row = f"| Railway | {BUTTON.format(code=code)} |"
    changed = 0
    for name in sorted(glob.glob(str(REPO_ROOT / "README*.md"))):
        p = pathlib.Path(name)
        lines = p.read_text(encoding="utf-8").split("\n")
        hits = [i for i, ln in enumerate(lines) if RAILWAY_ROW.match(ln)]
        if len(hits) != 1:
            print(f"  !! {p.name}: expected 1 Railway row, found {len(hits)} — skipped")
            continue
        if lines[hits[0]] == row:
            print(f"  == {p.name}: already up to date")
            continue
        lines[hits[0]] = row
        if not dry_run:
            p.write_text("\n".join(lines), encoding="utf-8")
        print(f"  {'--' if dry_run else 'ok'} {p.name}")
        changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="publish_railway_template.py",
        description="Publish the Railway template and update the Deploy buttons.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage\n-----\n", 1)[1],
    )
    ap.add_argument("--list-projects", action="store_true",
                    help="list the account's projects and environments, then exit")
    ap.add_argument("--project-id", help="Railway project to snapshot into a template")
    ap.add_argument("--environment-id", help="environment within that project (default: its base)")
    ap.add_argument("--code", help="skip the API and use this already-published template code")
    ap.add_argument("--category", default="AI/ML",
                    help="marketplace category (default: %(default)s)")
    ap.add_argument("--write-readmes", action="store_true",
                    help="rewrite the Railway row in every README*.md")
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = ap.parse_args(argv)

    if args.code:
        code = args.code
    else:
        if not (args.list_projects or args.project_id):
            ap.error("pass --list-projects, --project-id, or --code")
        token = os.environ.get("RAILWAY_TOKEN")
        if not token:
            print("RAILWAY_TOKEN is not set — create one at "
                  "https://railway.com/account/tokens", file=sys.stderr)
            return 2
        try:
            if args.list_projects:
                list_projects(token)
                return 0
            code = generate_and_publish(
                token, args.project_id, args.environment_id, args.category
            )
        except RailwayError as e:
            print(f"Railway API error: {e}", file=sys.stderr)
            return 1

    print(f"\ntemplate code: {code}")
    print(f"deploy URL   : https://railway.com/new/template/{code}\n")
    print("button markdown:")
    print("  " + BUTTON.format(code=code) + "\n")

    if args.write_readmes:
        n = write_readmes(code, args.dry_run)
        print(f"\n{n} README{'s' if n != 1 else ''} "
              f"{'would be ' if args.dry_run else ''}updated")
    else:
        print("re-run with --write-readmes to wire this into the twelve READMEs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
