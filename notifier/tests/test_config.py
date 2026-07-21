from notifier.config import load_notifier_config


def write_config(tmp_path, content: str):
    config_file = tmp_path / "notifier.yaml"
    config_file.write_text(content, encoding="utf-8")
    return config_file


def test_load_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(tmp_path, "notifier: {}\n")

    config = load_notifier_config()

    assert config.channels == {}
    assert config.rules == []


def test_load_channels_and_rules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        """
notifier:
  channels:
    slack:
      enabled: true
      credentials:
        webhook_url: https://hooks.slack.com/x
    discord: false
  rules:
    - name: servidores
      interval: 30
      cooldown: 600
      window_minutes: 10
      server:
        - type: cpu_percent
          warning: 70
          critical: 90
      database:
        - type: cache_hit_ratio
          databases:
            - app_db
            - analytics
      table:
        - type: growth_percent
          tables:
            - database: app_db
              schema: public
              table: users
            - app_db.audit.events
      index:
        - type: hit_rate
          database: app_db
          index: users_email_idx
""",
    )

    config = load_notifier_config()

    assert config.channels["slack"].enabled is True
    assert config.channels["discord"].enabled is False
    assert len(config.rules) == 1

    rule = config.rules[0]
    assert rule.interval == 30
    assert rule.cooldown == 600
    assert rule.window_minutes == 10
    assert len(rule.targets) == 4

    cpu = rule.targets[0]
    assert (cpu.scope, cpu.type) == ("server", "cpu_percent")
    assert cpu.names == []
    assert cpu.filters == {}
    assert (cpu.warning, cpu.critical) == (70.0, 90.0)

    cache = rule.targets[1]
    assert cache.names == [{"database": "app_db"}, {"database": "analytics"}]
    assert cache.direction == "below"

    growth = rule.targets[2]
    assert growth.names == [
        {"database": "app_db", "schema": "public", "table": "users"},
        {"database": "app_db", "schema": "audit", "table": "events"},
    ]

    hit = rule.targets[3]
    assert hit.names == [{"database": "app_db", "index": "users_email_idx"}]


def test_table_and_index_filters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        """
notifier:
  rules:
    - name: filtros
      table:
        - type: dead_tuple_ratio
          database: app_db
          schemas:
            - public
            - audit
          table_regex: "^fact_"
      index:
        - type: hit_rate
          database: app_db
          tables:
            - users
            - orders
          index_regex: "_pkey$"
""",
    )

    config = load_notifier_config()

    table_target, index_target = config.rules[0].targets
    assert table_target.names == []
    assert table_target.filters == {
        "database": "app_db",
        "schemas": ["public", "audit"],
        "table_regex": "^fact_",
    }
    assert index_target.names == []
    assert index_target.filters == {
        "database": "app_db",
        "tables": ["users", "orders"],
        "index_regex": "_pkey$",
    }


def test_names_take_precedence_over_filters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        """
notifier:
  rules:
    - name: precedencia
      table:
        - type: growth_percent
          tables:
            - public.users
          table_regex: "^fact_"
          schemas:
            - audit
""",
    )

    config = load_notifier_config()

    target = config.rules[0].targets[0]
    assert target.names == [{"schema": "public", "table": "users"}]
    assert target.filters == {}


def test_table_name_string_forms(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        """
notifier:
  rules:
    - name: formas
      table:
        - type: growth_percent
          tables:
            - users
            - public.orders
            - app_db.audit.events
""",
    )

    config = load_notifier_config()

    assert config.rules[0].targets[0].names == [
        {"schema": "public", "table": "users"},
        {"schema": "public", "table": "orders"},
        {"database": "app_db", "schema": "audit", "table": "events"},
    ]


def test_unknown_target_type_is_skipped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(
        tmp_path,
        """
notifier:
  rules:
    - name: teste
      server:
        - type: nao_existe
        - type: cpu_percent
""",
    )

    config = load_notifier_config()

    assert len(config.rules) == 1
    assert [t.type for t in config.rules[0].targets] == ["cpu_percent"]


def test_env_interpolation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TEST_WEBHOOK", "https://hooks.slack.com/secret")
    write_config(
        tmp_path,
        """
notifier:
  channels:
    slack:
      enabled: true
      credentials:
        webhook_url: ${TEST_WEBHOOK}
        missing: ${TEST_MISSING_VAR}
        with_default: ${TEST_MISSING_PORT:-587}
""",
    )

    config = load_notifier_config()

    credentials = config.channels["slack"].credentials
    assert credentials["webhook_url"] == "https://hooks.slack.com/secret"
    assert credentials["missing"] == ""
    assert credentials["with_default"] == "587"
