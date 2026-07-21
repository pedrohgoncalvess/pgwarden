from notifier.services.rules import RULE_TYPES, TODO_TYPES, _dead_tuple_ratio


def test_every_scope_type_pair_is_known():
    assert set(RULE_TYPES.keys()) == {
        ("server", "cpu_percent"),
        ("server", "ram_percent"),
        ("server", "disk_percent"),
        ("database", "growth_percent"),
        ("database", "cache_hit_ratio"),
        ("database", "deadlocks"),
        ("database", "tup_updated"),
        ("database", "tup_deleted"),
        ("database", "long_query_ms"),
        ("database", "waiting_sessions"),
        ("database", "blocked_locks"),
        ("database", "table_created"),
        ("database", "table_dropped"),
        ("database", "index_created"),
        ("database", "index_dropped"),
        ("table", "growth_percent"),
        ("table", "dead_tuples"),
        ("table", "dead_tuple_ratio"),
        ("table", "column_added"),
        ("index", "hit_rate"),
    }


def test_todo_types_have_no_rule_type():
    for key in TODO_TYPES:
        assert key not in RULE_TYPES


def test_every_rule_type_supports_window_and_entity_params():
    for rule_type in RULE_TYPES.values():
        assert ":window" in rule_type.query
        assert ":entity_id" in rule_type.query


def test_below_direction_types():
    below = {key for key, rt in RULE_TYPES.items() if rt.default_direction == "below"}
    assert below == {("database", "cache_hit_ratio"), ("index", "hit_rate")}


def test_dead_tuple_ratio_mapper():
    row = {"entity": "public.users", "n_dead_tup": 2000, "n_live_tup": 8000}
    entity, value = _dead_tuple_ratio(row)
    assert entity == "public.users"
    assert value == 0.2


def test_dead_tuple_ratio_mapper_empty_table():
    assert _dead_tuple_ratio({"entity": "public.t", "n_dead_tup": 0, "n_live_tup": 0}) is None


def test_simple_mapper_ignores_null_values():
    from notifier.services.rules import _simple

    mapper = _simple("entity", "value")
    assert mapper({"entity": "local", "value": None}) is None
    assert mapper({"entity": "local", "value": 42}) == ("local", 42.0)
