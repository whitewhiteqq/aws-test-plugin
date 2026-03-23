"""CLI entry point for aws-test-plugin."""

import shutil
import sys
from importlib.resources import files
from pathlib import Path


def _get_pkg_dir() -> Path:
    """Return the installed package directory (contains AGENTS.md, scripts/)."""
    return Path(str(files("aws_test_plugin")))


def _get_data_dir() -> Path:
    """Return the directory containing skills/ and agents/.

    In an installed wheel, force-include maps root skills/ and agents/ into
    the package directory.  During editable/development installs the package
    dir won't have them, so fall back to the repo root.
    """
    pkg = _get_pkg_dir()
    if (pkg / "skills").is_dir():
        return pkg
    # Editable install: src/aws_test_plugin -> repo root is two levels up
    repo_root = pkg.parent.parent
    if (repo_root / "skills").is_dir():
        return repo_root
    return pkg


def _copy_tree(src: Path, dst: Path, label: str) -> int:
    """Copy a directory tree, reporting what's copied. Returns file count."""
    count = 0
    for item in sorted(src.rglob("*")):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                print(f"  skip  {label}/{rel}  (already exists)")
            else:
                shutil.copy2(item, target)
                print(f"  +     {label}/{rel}")
                count += 1
    return count


def cmd_init(target: str, agents: list[str] | None = None) -> None:
    """Install skills and agents into a target project."""
    root = Path(target).resolve()
    data = _get_data_dir()

    agents_to_install = agents or ["claude", "copilot", "codex"]

    total = 0
    skills_src = data / "skills"
    agents_src = data / "agents"

    # Always install skills
    if skills_src.is_dir():
        for agent in agents_to_install:
            if agent in ("claude",):
                dst = root / ".claude" / "skills"
                total += _copy_tree(skills_src, dst, ".claude/skills")
            if agent in ("copilot",):
                dst = root / ".github" / "skills"
                total += _copy_tree(skills_src, dst, ".github/skills")

    # Install agent definitions
    if agents_src.is_dir():
        for agent in agents_to_install:
            if agent in ("claude",):
                dst = root / ".claude" / "agents"
                total += _copy_tree(agents_src, dst, ".claude/agents")
            if agent in ("copilot",):
                dst = root / ".github" / "agents"
                total += _copy_tree(agents_src, dst, ".github/agents")

    # For Codex: generate AGENTS.md if requested
    if "codex" in agents_to_install:
        agents_md = root / "AGENTS.md"
        if not agents_md.exists():
            # AGENTS.md lives in the package dir, not with skills/agents
            agents_md_src = _get_pkg_dir() / "AGENTS.md"
            if agents_md_src.exists():
                shutil.copy2(agents_md_src, agents_md)
                print("  +     AGENTS.md")
                total += 1

    print(f"\nInstalled {total} files into {root}")
    print("Next: pip install 'aws-test-plugin[test]'  (or uv sync --extra test)")


def cmd_list() -> None:
    """List available skills."""
    data = _get_data_dir()
    skills_dir = data / "skills"
    if not skills_dir.is_dir():
        print("No skills found.")
        return

    print("Available skills:\n")
    for skill in sorted(skills_dir.iterdir()):
        if skill.is_dir() and (skill / "SKILL.md").exists():
            # Read first line of description from frontmatter
            desc = ""
            in_frontmatter = False
            in_desc = False
            for line in (skill / "SKILL.md").read_text(encoding="utf-8").splitlines():
                if line.strip() == "---" and not in_frontmatter:
                    in_frontmatter = True
                    continue
                if line.strip() == "---" and in_frontmatter:
                    break
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip(">").strip()
                    in_desc = True
                    continue
                if in_desc and line.startswith("  "):
                    desc += " " + line.strip()
                    continue
                if in_desc:
                    in_desc = False

            refs = list((skill / "references").glob("*.md")) if (skill / "references").is_dir() else []
            print(f"  {skill.name}")
            if desc:
                print(f"    {desc[:100]}")
            if refs:
                print(f"    references: {', '.join(r.stem for r in refs)}")
            print()


def cmd_scaffold(target: str) -> None:
    """Run the scaffold script to discover and set up test directories."""
    # Scripts live in the package dir, not with skills/agents
    pkg = _get_pkg_dir()
    scaffold_script = pkg / "scripts" / "scaffold.py"
    if not scaffold_script.exists():
        print("Error: scaffold.py not found in package data.")
        sys.exit(1)

    # Import and run scaffold.main() directly
    import importlib.util

    spec = importlib.util.spec_from_file_location("scaffold", scaffold_script)
    if spec is None or spec.loader is None:
        print("Error: unable to load scaffold.py from package data.")
        sys.exit(1)

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.argv = ["scaffold", "--project-root", target]
    mod.main()


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="aws-test-plugin",
        description="Install AWS test skills for AI coding agents (Claude Code, GitHub Copilot, Codex)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Install skills and agents into a project")
    p_init.add_argument("target", nargs="?", default=".", help="Project root (default: .)")
    p_init.add_argument(
        "--agent",
        "-a",
        action="append",
        choices=["claude", "copilot", "codex", "all"],
        help="Which agent(s) to install for (default: all). Repeatable.",
    )

    # list
    sub.add_parser("list", help="List available skills")

    # scaffold
    p_scaffold = sub.add_parser("scaffold", help="Scaffold test directories for an AWS project")
    p_scaffold.add_argument("target", nargs="?", default=".", help="Project root (default: .)")

    args = parser.parse_args()

    if args.command == "init":
        agents = args.agent or ["all"]
        if "all" in agents:
            agents = ["claude", "copilot", "codex"]
        cmd_init(args.target, agents)
    elif args.command == "list":
        cmd_list()
    elif args.command == "scaffold":
        cmd_scaffold(args.target)


if __name__ == "__main__":
    main()
