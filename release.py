#!/usr/bin/env python3
"""
CoraRS Release Automation
Automatiza: commit, version bump, tag, push e release no GitHub.

Uso:
    python release.py                    # menu interativo
    python release.py 0.2.6              # versao direta
    python release.py 0.2.6 --beta       # prerelease
    python release.py 0.2.6 --dry-run    # mostra o que faria sem fazer
    python release.py --upload ./dist    # upload de artefatos para ultima release
    python release.py --path ../corars   # especificar caminho do projeto
"""

import subprocess
import sys
import os
import json
import re
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    print("Instalando requests...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ── Config ──────────────────────────────────────────────────────────────────
REPO_OWNER = "coracowork"
REPO_NAME = "corars"
DEFAULT_BRANCH = "main"

# Build targets
TARGETS = {
    "linux-x64": "x86_64-unknown-linux-gnu",
    "linux-arm64": "aarch64-unknown-linux-gnu",
    "macos-x64": "x86_64-apple-darwin",
    "macos-arm64": "aarch64-apple-darwin",
    "windows-x64": "x86_64-pc-windows-msvc",
    "windows-arm64": "aarch64-pc-windows-msvc",
}

RUST_VERSION = "1.96.1"
PACKAGE_NAME = "cora-cli"


# ── Detecção do projeto ──────────────────────────────────────────────────
def find_project_root(start_path: Path = None) -> Path:
    """Procura a raiz do projeto (onde está Cargo.toml)."""
    if start_path is None:
        start_path = Path.cwd()
    
    # Primeiro verifica se o diretório atual já é o projeto
    if (start_path / "Cargo.toml").exists():
        return start_path
    
    # Procura em diretórios comuns
    search_paths = [
        start_path / "corars",
        start_path / "../corars",
        start_path / "../../corars",
        start_path / "../cora-rs",
        start_path / "../CoraRS",
        start_path.parent / "corars",
        Path.home() / "dev/corars",
        Path.home() / "projects/corars",
    ]
    
    for path in search_paths:
        if path.exists() and (path / "Cargo.toml").exists():
            return path.resolve()
    
    # Procura recursivamente (limitado a 3 níveis)
    for path in start_path.glob("**/Cargo.toml"):
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            if '[workspace]' in content and 'members' in content:
                return path.parent
            if 'name = "cora-cli"' in content or 'name = "corars"' in content:
                return path.parent
    
    return None


def clone_repo(target_dir: Path = None):
    """Clona o repositório caso não exista."""
    if target_dir is None:
        target_dir = Path.cwd() / REPO_NAME
    
    if target_dir.exists():
        print(f"✅ Repositório já existe em {target_dir}")
        return target_dir
    
    print(f"📦 Clonando {REPO_OWNER}/{REPO_NAME}...")
    repo_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
    try:
        subprocess.run(
            f"git clone {repo_url} {target_dir}",
            shell=True,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✅ Clonado para {target_dir}")
        return target_dir
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao clonar: {e.stderr}")
        sys.exit(1)


# ── Helpers ─────────────────────────────────────────────────────────────────
def run(cmd: str, check=True, capture=False, cwd=None) -> subprocess.CompletedProcess:
    """Executa comando no shell."""
    cwd = str(cwd) if cwd else None
    result = subprocess.run(
        cmd, shell=True, capture_output=capture, text=True, encoding="utf-8",
        cwd=cwd,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if capture else ""
        print(f"  ERRO: {cmd}")
        if stderr:
            print(f"  {stderr[:500]}")
        sys.exit(1)
    return result


def get_current_version(project_root: Path) -> str:
    """Le a versao atual do Cargo.toml."""
    cargo_toml = project_root / "Cargo.toml"
    content = cargo_toml.read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    if match:
        return match.group(1)
    return "0.0.0"


def set_version(project_root: Path, version: str):
    """Atualiza versao em todos os arquivos relevantes."""
    cargo_toml = project_root / "Cargo.toml"
    
    # 1. Cargo.toml
    content = cargo_toml.read_text(encoding="utf-8")
    new_content = re.sub(
        r'(\[workspace\.package\]\s*\n.*?version\s*=\s*")[^"]+(")',
        rf'\g<1>{version}\2',
        content,
        count=1,
        flags=re.DOTALL,
    )
    if new_content == content:
        new_content = content.replace(
            f'version = "{get_current_version(project_root)}"',
            f'version = "{version}"',
            1,
        )
    cargo_toml.write_text(new_content, encoding="utf-8")
    print(f"  Cargo.toml -> {version}")

    # 2. .release-please-manifest.json (se existir)
    manifest_file = project_root / ".release-please-manifest.json"
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest["."] = version
        manifest_file.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        print(f"  .release-please-manifest.json -> {version}")

    # 3. CHANGELOG.md (se existir)
    changelog = project_root / "CHANGELOG.md"
    if changelog.exists():
        content = changelog.read_text(encoding="utf-8")
        new_content = re.sub(
            r'## \[(\d+\.\d+\.\d+)\]',
            f'## [{version}]',
            content,
            count=1,
        )
        if new_content != content:
            changelog.write_text(new_content, encoding="utf-8")
            print(f"  CHANGELOG.md -> {version}")

    # 4. Atualizar Cargo.lock
    print("  Atualizando Cargo.lock...")
    run("cargo update --workspace", check=False, cwd=project_root)


def validate_version(v: str) -> bool:
    """Valida formato semver."""
    return bool(re.match(r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$', v))


def get_github_token() -> str:
    """Pega token do ambiente ou pede ao usuario."""
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        token = os.environ.get(var, "").strip()
        if token:
            return token

    result = run("gh auth token", check=False, capture=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    print("\n  Token do GitHub necessario.")
    print("  Opcoes:")
    print("    1. Exporte: export GITHUB_TOKEN=ghp_xxx")
    print("    2. Instale gh: https://cli.github.com/")
    print("    3. Cole o token abaixo:")
    token = input("  GITHUB_TOKEN> ").strip()
    if not token:
        print("  Saindo.")
        sys.exit(1)
    return token


def git_has_changes(project_root: Path) -> bool:
    result = run("git status --porcelain", check=False, capture=True, cwd=project_root)
    return bool(result.stdout.strip())


def get_changed_files(project_root: Path) -> list[str]:
    result = run("git status --porcelain", check=False, capture=True, cwd=project_root)
    files = []
    for line in result.stdout.strip().splitlines():
        if line.strip():
            status = line[:2].strip()
            filename = line[3:].strip()
            files.append(f"  [{status}] {filename}")
    return files


def tag_exists(project_root: Path, tag: str) -> bool:
    result = run(f"git tag -l {tag}", check=False, capture=True, cwd=project_root)
    if result.stdout.strip():
        return True
    result = run(f"git ls-remote --tags origin {tag}", check=False, capture=True, cwd=project_root)
    return tag in result.stdout


def inc_version(version: str, bump: str) -> str:
    parts = version.split("-")[0].split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump == "major":
        return f"{major + 1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


# ── GitHub API ──────────────────────────────────────────────────────────────
def github_api(method: str, endpoint: str, token: str, **kwargs) -> dict | None:
    url = f"https://api.github.com{endpoint}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    if resp.status_code in (200, 201):
        return resp.json()
    if resp.status_code == 422:
        return None
    print(f"  GitHub API {resp.status_code}: {resp.text[:300]}")
    return None


def create_github_release(
    tag: str, token: str, prerelease=False, files: list[str] | None = None
) -> str | None:
    print(f"\n  Criando release {tag}...")

    targets_list = "\n".join(
        f"| `{t}` | {p} |"
        for p, t in TARGETS.items()
    )
    
    # Corrigido: f-string com múltiplas linhas agora usa join para evitar erro de sintaxe
    body_lines = [
        f"## CoraRS {tag}",
        "",
        "Build automatico via CI/CD.",
        "",
        "### Plataformas suportadas",
        "",
        "| Target | Plataforma |",
        "|--------|------------|",
        targets_list,
        "",
        "### SHA256",
        "Os checksums `.sha256` sao gerados automaticamente para cada artefato.",
        "",
        "### Instalacao",
        "",
        "**Linux / macOS:**",
        "```bash",
        f"tar xzf CoraRS-{tag}-<target>.tar.gz",
        "chmod +x corars",
        "sudo mv corars /usr/local/bin/",
        "```",
        "",
        "**Windows:**",
        "```powershell",
        f"Expand-Archive CoraRS-{tag}-<target>.zip -DestinationPath .",
        "```",
    ]
    body = "\n".join(body_lines)

    payload = {
        "tag_name": tag,
        "name": f"Release {tag}",
        "body": body,
        "draft": False,
        "prerelease": prerelease,
    }

    data = github_api(
        "POST", f"/repos/{REPO_OWNER}/{REPO_NAME}/releases", token, json=payload
    )
    if not data:
        print("  Release pode ja existir. Verificando...")
        data = github_api(
            "GET", f"/repos/{REPO_OWNER}/{REPO_NAME}/releases/tags/{tag}", token
        )
        if data:
            return data.get("html_url")
        return None

    release_url = data.get("html_url", "")
    upload_url = data.get("upload_url", "")
    print(f"  Release criada: {release_url}")

    if files and upload_url:
        for filepath in files:
            if not Path(filepath).exists():
                print(f"  Pulando {filepath} (nao encontrado)")
                continue
            filename = Path(filepath).name
            size_mb = Path(filepath).stat().st_size / (1024 * 1024)
            print(f"  Uploading {filename} ({size_mb:.1f} MB)...")
            upload_endpoint = upload_url.replace("{?name,label}", f"?name={filename}")
            headers = {
                "Authorization": f"token {token}",
                "Content-Type": "application/octet-stream",
            }
            with open(filepath, "rb") as f:
                resp = requests.post(upload_endpoint, headers=headers, data=f, timeout=600)
            print("    OK" if resp.status_code in (200, 201) else f"    Falhou ({resp.status_code})")

    return release_url


def upload_release_assets(release_id: int, token: str, directory: str):
    dirpath = Path(directory)
    if not dirpath.exists():
        print(f"  Diretorio nao encontrado: {directory}")
        return

    artifacts = sorted(dirpath.glob("*.*"))
    if not artifacts:
        print(f"  Nenhum artefato em {directory}")
        return

    print(f"\n  Uploading {len(artifacts)} artefatos...")
    for artifact in artifacts:
        size_mb = artifact.stat().st_size / (1024 * 1024)
        print(f"    {artifact.name} ({size_mb:.1f} MB)...", end=" ", flush=True)
        headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/octet-stream",
        }
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/{release_id}/assets?name={artifact.name}"
        with open(artifact, "rb") as f:
            resp = requests.post(url, headers=headers, data=f, timeout=600)
        print("OK" if resp.status_code in (200, 201) else f"Falhou ({resp.status_code})")


def get_latest_release_id(token: str) -> int | None:
    data = github_api("GET", f"/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest", token)
    return data.get("id") if data else None


# ── Fluxo principal ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="CoraRS Release Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python release.py                        # menu interativo
  python release.py 0.2.6                  # versao especifica
  python release.py 0.2.6 --beta           # prerelease
  python release.py 0.2.6 --dry-run        # simular sem alterar
  python release.py --upload ./dist        # upload artefatos para ultima release
  python release.py --path ../corars       # especificar caminho do projeto
        """,
    )
    parser.add_argument("version", nargs="?", help="Versao (ex: 0.2.6)")
    parser.add_argument("--beta", action="store_true", help="Marcar como prerelease")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem alterar")
    parser.add_argument("--upload", metavar="DIR", help="Upload artefatos de DIR para ultima release")
    parser.add_argument("--path", metavar="PATH", help="Caminho do projeto CoraRS")
    parser.add_argument("--skip-checks", action="store_true", help="Pular verificacoes antes de commit")
    parser.add_argument("--no-tag", action="store_true", help="Nao criar tag")
    parser.add_argument("--no-release", action="store_true", help="Nao criar release (so push + tag)")
    parser.add_argument("--force-tag", action="store_true", help="Deletar tag existente e recriar")
    parser.add_argument("--clone", action="store_true", help="Clonar repositorio se nao existir")
    args = parser.parse_args()

    print("=" * 60)
    print("  CoraRS Release Automation")
    print("=" * 60)

    # ── Encontrar o projeto ──────────────────────────────────────────────
    project_root = None
    if args.path:
        project_root = Path(args.path).resolve()
        if not (project_root / "Cargo.toml").exists():
            print(f"❌ Cargo.toml nao encontrado em {project_root}")
            sys.exit(1)
    else:
        project_root = find_project_root()
        if project_root is None:
            print("❌ Projeto CoraRS nao encontrado.")
            if args.clone:
                print("📦 Clonando repositorio...")
                project_root = clone_repo(Path.cwd() / REPO_NAME)
            else:
                print("\n  Use --path para especificar o caminho ou --clone para clonar.")
                print(f"  Exemplo: python release.py --path ../{REPO_NAME}")
                sys.exit(1)

    print(f"\n📁 Projeto encontrado: {project_root}")

    # Verifica se é um repositório Git
    if not (project_root / ".git").exists():
        print("❌ Nao e um repositorio Git. Inicializando...")
        run("git init", cwd=project_root)
        run(f"git remote add origin https://github.com/{REPO_OWNER}/{REPO_NAME}.git", cwd=project_root)
        print("✅ Git inicializado.")

    # ── Modo: upload de artefatos ──────────────────────────────────────
    if args.upload:
        token = get_github_token()
        release_id = get_latest_release_id(token)
        if release_id:
            upload_release_assets(release_id, token, args.upload)
        else:
            print("  Nenhuma release encontrada. Crie uma primeiro.")
        return

    # ── Definir versao ──────────────────────────────────────────────────
    current = get_current_version(project_root)
    print(f"\n  Versao atual: {current}")
    print(f"  Rust toolchain: {RUST_VERSION}")
    print(f"  Binario: {PACKAGE_NAME}")

    if args.version:
        new_version = args.version
    else:
        print("\n  Opcoes:")
        print(f"    1) Major:  incrementar para {inc_version(current, 'major')}")
        print(f"    2) Minor:  incrementar para {inc_version(current, 'minor')}")
        print(f"    3) Patch:  incrementar para {inc_version(current, 'patch')}")
        print(f"    4) Manual: digitar versao")
        choice = input("\n  Escolha [1-4]: ").strip()

        bumps = {"1": "major", "2": "minor", "3": "patch"}
        if choice in bumps:
            new_version = inc_version(current, bumps[choice])
        elif choice == "4":
            new_version = input("  Versao: ").strip()
        else:
            print("  Opcao invalida.")
            return

    if not validate_version(new_version):
        print(f"  Versao invalida: {new_version}")
        return

    tag = f"v{new_version}"
    print(f"\n  Nova versao: {new_version}")
    print(f"  Tag:         {tag}")
    print(f"  Prerelease:  {'Sim' if args.beta else 'Nao'}")

    # ── Verificar estado do repo ────────────────────────────────────────
    print("\n─── Status do Repositorio ───")
    branch = run("git branch --show-current", capture=True, cwd=project_root).stdout.strip()
    if not branch:
        branch = DEFAULT_BRANCH
        print(f"  Branch:  {branch} (padrao)")
    else:
        print(f"  Branch:  {branch}")

    remote = run("git remote get-url origin", capture=True, cwd=project_root).stdout.strip()
    print(f"  Remote:  {remote}")

    has_changes = git_has_changes(project_root)
    if has_changes:
        print(f"\n  Mudancas nao commitadas:")
        for f in get_changed_files(project_root):
            print(f"    {f}")
    else:
        print("  Working tree limpo.")

    # ── Arquivos que serao atualizados ──────────────────────────────────
    print("\n─── Arquivos de Versao ───")
    print(f"  Cargo.toml:                          {current} -> {new_version}")
    manifest_file = project_root / ".release-please-manifest.json"
    if manifest_file.exists():
        print(f"  .release-please-manifest.json:       {current} -> {new_version}")
    changelog_file = project_root / "CHANGELOG.md"
    if changelog_file.exists():
        print(f"  CHANGELOG.md:                        (atualizar cabecalho)")
    print(f"  Cargo.lock:                          (auto-update via cargo)")

    # ── Resumo e confirmacao ────────────────────────────────────────────
    print("\n─── Plano de Execucao ───")
    steps = []
    if has_changes:
        steps.append("1. git add . && git commit (mudancas pendentes)")
    n = len(steps) + 1
    steps.append(f"{n}. Atualizar versao em Cargo.toml + manifest")
    n += 1
    steps.append(f"{n}. cargo update --workspace (atualizar Cargo.lock)")
    n += 1
    steps.append(f"{n}. git add . && git commit (chore(release): v{new_version})")
    if not args.no_tag:
        if tag_exists(project_root, tag) and not args.force_tag:
            steps.append(f"  ! Tag {tag} ja existe! Use --force-tag para recriar.")
        elif tag_exists(project_root, tag) and args.force_tag:
            n += 1
            steps.append(f"{n}. Deletar tag {tag} existente")
        n += 1
        steps.append(f"{n}. git tag -a {tag} -m 'Release {tag}'")
    n += 1
    steps.append(f"{n}. git push origin {branch}")
    if not args.no_tag:
        n += 1
        steps.append(f"{n}. git push origin {tag}")
    if not args.no_release:
        n += 1
        steps.append(f"{n}. Criar GitHub Release {tag}")
    n += 1
    steps.append(f"{n}. Actions CI compila para {len(TARGETS)} plataformas:")

    for s in steps:
        print(f"  {s}")

    if args.dry_run:
        print("\n  [DRY RUN] Nenhuma alteracao feita.")
        return

    confirm = input("\n  Confirmar? [s/N]: ").strip().lower()
    if confirm not in ("s", "sim", "y", "yes"):
        print("  Cancelado.")
        return

    # ── Executar ────────────────────────────────────────────────────────
    step_num = 0

    def log_step(msg):
        nonlocal step_num
        step_num += 1
        print(f"\n  [{step_num}] {msg}")

    # 1. Checks
    if not args.skip_checks and has_changes:
        log_step("Lint + Format check...")
        run("cargo fmt --all -- --check", check=False, cwd=project_root)
        run("cargo clippy --workspace -- -D warnings", check=False, cwd=project_root)

    # 2. Commit mudancas pendentes
    if has_changes:
        log_step("Commitando mudancas pendentes...")
        run("git add .", cwd=project_root)
        run('git commit -m "chore: pre-release updates"', cwd=project_root)

    # 3. Atualizar versao
    log_step(f"Atualizando versao para {new_version}...")
    set_version(project_root, new_version)

    # 4. Commit versao
    log_step("Commitando versao...")
    run("git add .", cwd=project_root)
    run(f'git commit -m "chore(release): v{new_version}" --allow-empty', cwd=project_root)

    # 5. Tag
    if not args.no_tag:
        if tag_exists(project_root, tag) and args.force_tag:
            log_step(f"Deletando tag {tag} existente...")
            run(f"git tag -d {tag}", check=False, cwd=project_root)
            run(f"git push origin :refs/tags/{tag}", check=False, cwd=project_root)

        log_step(f"Criando tag {tag}...")
        run(f'git tag -a {tag} -m "Release {tag}"', cwd=project_root)

    # 6. Push
    log_step(f"Push para origin/{branch}...")
    run(f"git push origin {branch}", cwd=project_root)
    if not args.no_tag:
        run(f"git push origin {tag}", cwd=project_root)

    # 7. Release
    release_url = None
    if not args.no_release:
        log_step("Criando GitHub Release...")
        token = get_github_token()
        release_url = create_github_release(tag, token, prerelease=args.beta)

    # ── Resultado ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ✅ RELEASE CONCLUIDA!")
    print("=" * 60)
    print(f"\n  Versao:  {new_version}")
    print(f"  Tag:     {tag}")
    if release_url:
        print(f"  Release: {release_url}")
    print(f"\n  Actions CI esta compilando para:")
    for name, target in TARGETS.items():
        print(f"    - {name}: {target}")
    print(f"\n  Artefatos gerados:")
    print(f"    - CoraRS-{tag}-<target>.tar.gz (Linux/macOS)")
    print(f"    - CoraRS-{tag}-<target>.zip (Windows)")
    print(f"    - CoraRS-{tag}-<target>.sha256 (checksums)")
    print(f"\n  Acompanhe: https://github.com/{REPO_OWNER}/{REPO_NAME}/actions")
    print()


if __name__ == "__main__":
    main()