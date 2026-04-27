#!/usr/bin/env python3
"""
ローカル Claude Code で PR をレビューして GitHub にコメントを投稿するスクリプト。

使い方:
    python scripts/review.py --pr <PR番号>

必要な環境変数（.env ファイルに書く）:
    GITHUB_TOKEN=ghp_...
    GITHUB_REPO=owner/repo-name
"""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO  = os.environ["GITHUB_REPO"]
PROMPT_FILE  = Path(__file__).parent.parent / ".claude" / "review-prompt.md"


def get_pr_diff(pr_number: int) -> str:
    """GitHub API から PR の diff を取得する。"""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.diff",
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls/{pr_number}"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.text


def run_claude_review(diff: str) -> dict:
    """Claude Code をローカルで実行して review 結果を取得する。"""
    prompt = PROMPT_FILE.read_text(encoding="utf-8")

    full_prompt = f"{prompt}\n\n## PR Diff\n\n```diff\n{diff}\n```"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(full_prompt)
        prompt_path = f.name

    try:
        result = subprocess.run(
            ["claude", "--print", "--no-markdown", prompt_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"[警告] Claude Code エラー: {result.stderr}")
            return {
                "verdict": "error",
                "summary": f"Claude Code の実行に失敗しました: {result.stderr[:200]}",
                "issues": [],
            }
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        # JSON でない場合はそのまま summary として使う
        return {
            "verdict": "unknown",
            "summary": result.stdout.strip()[:500],
            "issues": [],
        }
    finally:
        os.unlink(prompt_path)


def build_comment(review: dict) -> str:
    """PR に投稿する markdown コメントを組み立てる。"""
    verdict = review.get("verdict", "unknown")
    summary = review.get("summary", "")
    issues  = review.get("issues", [])

    emoji = "✅" if verdict == "approve" else "❌" if verdict == "request_changes" else "⚠️"

    lines = [
        f"{emoji} **Claude Code Review**",
        "",
        summary,
    ]

    if issues:
        lines += ["", "### Issues found", ""]
        for issue in issues:
            sev  = issue.get("severity", "info").upper()
            f    = issue.get("file", "?")
            ln   = issue.get("line", "?")
            msg  = issue.get("message", "")
            fix  = issue.get("fix", "")
            lines.append(f"- **{sev}** `{f}` line {ln}: {msg}")
            if fix:
                lines.append(f"  > Fix: `{fix}`")

    lines += ["", "---", "*Posted by Claude Code (claude.ai Pro — local)*"]
    return "\n".join(lines)


def post_comment(pr_number: int, body: str) -> None:
    """GitHub API で PR にコメントを投稿する。"""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues/{pr_number}/comments"
    resp = requests.post(url, headers=headers, json={"body": body})
    resp.raise_for_status()
    print(f"✅ コメントを投稿しました: {resp.json()['html_url']}")


def main():
    parser = argparse.ArgumentParser(description="Claude Code で PR をレビューする")
    parser.add_argument("--pr", type=int, required=True, help="PR 番号")
    args = parser.parse_args()

    print(f"📥 PR #{args.pr} の diff を取得中...")
    diff = get_pr_diff(args.pr)
    print(f"   diff サイズ: {len(diff)} chars")

    print("🤖 Claude Code でレビュー中...")
    review = run_claude_review(diff)
    print(f"   verdict: {review.get('verdict')} / issues: {len(review.get('issues', []))}")

    print("💬 PR にコメントを投稿中...")
    comment = build_comment(review)
    post_comment(args.pr, comment)


if __name__ == "__main__":
    main()