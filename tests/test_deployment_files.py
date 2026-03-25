import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILE_TARGET = (
    r'(?:\$\{?DATA_DIR\}?[^\s"\']*|/app/data[^\s"\']*|'
    r'allowed_users\.txt|user_settings\.json|strategy\.log|'
    r'last_can_biao_xiu_state_[^\s"\']*)'
)
FORBIDDEN_RUNTIME_BOOTSTRAP_PATTERNS = {
    "touch": rf"(?m)^\s*touch\b.*{RUNTIME_FILE_TARGET}",
    "truncate": rf"(?m)^\s*truncate\b.*{RUNTIME_FILE_TARGET}",
    "tee": rf"(?m)^\s*tee\b.*{RUNTIME_FILE_TARGET}",
    "install or copy": rf"(?m)^\s*(?:install|cp)\b.*{RUNTIME_FILE_TARGET}",
    "shell redirection": rf"(?m)^\s*(?::|(?:printf|echo|cat))\b.*(?:>>?|>\|).*{RUNTIME_FILE_TARGET}",
}


class DeploymentFileTests(unittest.TestCase):
    def read_repo_file(self, relative_path):
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def assert_no_runtime_file_bootstrap(self, entrypoint):
        for bootstrap_style, pattern in FORBIDDEN_RUNTIME_BOOTSTRAP_PATTERNS.items():
            self.assertNotRegex(
                entrypoint,
                re.compile(pattern),
                f"docker-entrypoint.sh must not pre-create runtime files via {bootstrap_style}",
            )

    def test_dockerfile_sets_default_container_data_dir_and_entrypoint(self):
        dockerfile = self.read_repo_file("Dockerfile")

        self.assertIn("DATA_DIR=/app/data", dockerfile)
        self.assertRegex(
            dockerfile,
            re.compile(
                r"ENV\s+PYTHONDONTWRITEBYTECODE=1\s*\\\s*\n\s*PYTHONUNBUFFERED=1\s*\\\s*\n\s*DATA_DIR=/app/data"
            ),
        )
        self.assertIn("COPY docker-entrypoint.sh /app/docker-entrypoint.sh", dockerfile)
        self.assertIn("RUN chmod +x /app/docker-entrypoint.sh", dockerfile)
        self.assertIn('ENTRYPOINT ["/app/docker-entrypoint.sh"]', dockerfile)

    def test_entrypoint_validates_required_vars_without_indirect_expansion(self):
        entrypoint = self.read_repo_file("docker-entrypoint.sh")

        self.assertIn('require_env "TG_BOT_TOKEN" "${TG_BOT_TOKEN:-}"', entrypoint)
        self.assertIn('require_env "TG_CHAT_ID" "${TG_CHAT_ID:-}"', entrypoint)
        self.assertIn(
            'require_env "SUBSCRIBE_PASSWORD" "${SUBSCRIBE_PASSWORD:-}"',
            entrypoint,
        )
        self.assertNotRegex(entrypoint, re.compile(r"\b" + "e" + "val" + r"\b"))

    def test_entrypoint_uses_data_dir_without_symlinks_or_runtime_file_bootstrap(self):
        entrypoint = self.read_repo_file("docker-entrypoint.sh")

        self.assertIn('DATA_DIR="${DATA_DIR:-/app/data}"', entrypoint)
        self.assertIn('mkdir -p "$DATA_DIR" "$DATA_DIR/tmp"', entrypoint)
        self.assertNotRegex(entrypoint, re.compile(r"\bln\s+-s[f]?\b"))
        self.assert_no_runtime_file_bootstrap(entrypoint)

    def test_entrypoint_execs_python_main(self):
        entrypoint = self.read_repo_file("docker-entrypoint.sh")

        self.assertRegex(entrypoint, re.compile(r"exec python main\.py\s*$"))

    def test_docker_compose_keeps_env_file_and_runtime_mappings(self):
        compose_file = self.read_repo_file("docker-compose.yml")

        self.assertIn("env_file:", compose_file)
        self.assertIn("- .env", compose_file)
        self.assertIn("TG_BOT_TOKEN: ${TG_BOT_TOKEN:-}", compose_file)
        self.assertIn("TG_CHAT_ID: ${TG_CHAT_ID:-}", compose_file)
        self.assertIn("SUBSCRIBE_PASSWORD: ${SUBSCRIBE_PASSWORD:-}", compose_file)
        self.assertIn("LOGLEVEL: ${LOGLEVEL:-INFO}", compose_file)
        self.assertIn("MAX_WORKERS: ${MAX_WORKERS:-8}", compose_file)


    def test_docker_compose_mounts_and_pins_container_data_dir(self):
        compose_file = self.read_repo_file("docker-compose.yml")

        self.assertIn("DATA_DIR: /app/data", compose_file)
        self.assertIn("- ./data:/app/data", compose_file)

    def test_dockerignore_excludes_runtime_state_inputs(self):
        dockerignore = self.read_repo_file(".dockerignore")
        entries = {line.strip() for line in dockerignore.splitlines() if line.strip()}

        self.assertIn(".env", entries)
        self.assertIn("data/", entries)
        self.assertIn("allowed_users.txt", entries)
        self.assertIn("user_settings.json", entries)
        self.assertIn(".git", entries)
        self.assertIn(".git/", entries)

    def test_env_example_documents_optional_data_dir_usage(self):
        env_example = self.read_repo_file(".env.example")

        self.assertIn("# 数据目录（可选）", env_example)
        self.assertIn(
            "# 仅在 ClawCloud / docker run / 本地 python 运行时按需覆盖。",
            env_example,
        )
        self.assertIn(
            "# 使用 docker compose 时已固定挂载到 /app/data，不应在 .env 中设置。",
            env_example,
        )
        self.assertIn("# DATA_DIR=/app/data", env_example)


if __name__ == "__main__":
    unittest.main()
