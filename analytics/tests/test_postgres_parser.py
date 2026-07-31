from analytics.parser import ColumnMeta, TableMeta, parse_postgres_query


def metadata():
    users = TableMeta(
        id=1,
        schema_name="public",
        name="users",
        columns=(
            ColumnMeta(id=10, name="id"),
            ColumnMeta(id=11, name="name"),
            ColumnMeta(id=12, name="email"),
        ),
    )
    orders = TableMeta(
        id=2,
        schema_name="sales",
        name="orders",
        columns=(
            ColumnMeta(id=20, name="id"),
            ColumnMeta(id=21, name="user_id", fk_table_id=1, fk_column_id=10),
            ColumnMeta(id=22, name="status"),
            ColumnMeta(id=23, name="total"),
        ),
    )
    products = TableMeta(
        id=3,
        schema_name="inventory",
        name="products",
        columns=(
            ColumnMeta(id=30, name="id"),
            ColumnMeta(id=31, name="sku"),
            ColumnMeta(id=32, name="name"),
        ),
    )
    order_items = TableMeta(
        id=4,
        schema_name="sales",
        name="order_items",
        columns=(
            ColumnMeta(id=40, name="id"),
            ColumnMeta(id=41, name="order_id", fk_table_id=2, fk_column_id=20),
            ColumnMeta(id=42, name="product_id", fk_table_id=3, fk_column_id=30),
            ColumnMeta(id=43, name="qty"),
        ),
    )
    quoted = TableMeta(
        id=5,
        schema_name="crm",
        name="Customer Account",
        columns=(
            ColumnMeta(id=50, name="Account ID"),
            ColumnMeta(id=51, name="Display Name"),
        ),
    )
    return [users, orders, products, order_items, quoted]


def columns(parsed):
    return {(item.schema_name, item.table_name, item.column_name): item for item in parsed.columns}


def tables(parsed):
    return {(item.schema_name, item.table_name): item for item in parsed.tables}


def test_simple_alias_select_and_where_condition():
    parsed = parse_postgres_query(
        "select u.id, u.email from public.users u where u.email ilike '%@example.com'",
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("public", "users", "id")].is_selected
    assert cols[("public", "users", "email")].is_selected
    assert cols[("public", "users", "email")].is_condition


def test_select_star_expands_all_columns_from_single_table():
    parsed = parse_postgres_query("select * from public.users", metadata())
    cols = columns(parsed)
    assert set(cols) == {
        ("public", "users", "id"),
        ("public", "users", "name"),
        ("public", "users", "email"),
    }
    assert all(item.is_selected for item in cols.values())


def test_qualified_star_expands_only_that_table():
    parsed = parse_postgres_query(
        "select u.*, o.status from public.users u join sales.orders o on o.user_id = u.id",
        metadata(),
    )
    cols = columns(parsed)
    assert ("public", "users", "name") in cols
    assert ("sales", "orders", "status") in cols
    assert ("sales", "orders", "total") not in cols


def test_join_condition_marks_foreign_columns_and_tables():
    parsed = parse_postgres_query(
        "select u.name, o.total from sales.orders o join public.users u on o.user_id = u.id",
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("sales", "orders", "user_id")].is_condition
    assert cols[("sales", "orders", "user_id")].is_condition_foreign
    assert cols[("public", "users", "id")].is_condition_foreign
    tbls = tables(parsed)
    assert tbls[("sales", "orders")].is_foreign
    assert tbls[("public", "users")].is_foreign


def test_multiple_joins_mark_each_fk_path():
    parsed = parse_postgres_query(
        """
        select p.sku, oi.qty
        from sales.order_items oi
        join sales.orders o on oi.order_id = o.id
        join inventory.products p on oi.product_id = p.id
        where o.status = 'paid'
        """,
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("sales", "order_items", "order_id")].is_condition_foreign
    assert cols[("sales", "order_items", "product_id")].is_condition_foreign
    assert cols[("sales", "orders", "status")].is_condition


def test_non_fk_join_is_condition_but_not_foreign():
    parsed = parse_postgres_query(
        "select u.name, p.name from public.users u join inventory.products p on u.name = p.name",
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("public", "users", "name")].is_condition
    assert not cols[("public", "users", "name")].is_condition_foreign
    assert not tables(parsed)[("inventory", "products")].is_foreign


def test_quoted_schema_table_column_and_alias():
    parsed = parse_postgres_query(
        'select ca."Display Name" from crm."Customer Account" as ca where ca."Account ID" = 10',
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("crm", "Customer Account", "Display Name")].is_selected
    assert cols[("crm", "Customer Account", "Account ID")].is_condition


def test_long_alias_and_function_expression():
    parsed = parse_postgres_query(
        """
        select customer_orders.status, count(customer_orders.id) as order_count
        from sales.orders as customer_orders
        where customer_orders.total > 100
        group by customer_orders.status
        """,
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("sales", "orders", "status")].is_selected
    assert cols[("sales", "orders", "id")].is_selected
    assert cols[("sales", "orders", "total")].is_condition


def test_cte_parses_inner_base_table():
    parsed = parse_postgres_query(
        """
        with recent_orders as (
            select o.id, o.user_id from sales.orders o where o.status = 'paid'
        )
        select r.id from recent_orders r
        """,
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("sales", "orders", "id")].is_selected
    assert cols[("sales", "orders", "user_id")].is_selected
    assert cols[("sales", "orders", "status")].is_condition


def test_subquery_in_from_parses_inner_tables():
    parsed = parse_postgres_query(
        """
        select sq.id
        from (
            select u.id from public.users u where u.name = 'Pedro'
        ) sq
        """,
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("public", "users", "id")].is_selected
    assert cols[("public", "users", "name")].is_condition


def test_unqualified_column_resolves_when_unique():
    parsed = parse_postgres_query("select email from users where email is not null", metadata())
    cols = columns(parsed)
    assert cols[("public", "users", "email")].is_selected
    assert cols[("public", "users", "email")].is_condition


def test_comma_join_style_conditions():
    parsed = parse_postgres_query(
        """
        select u.name, o.id
        from public.users u, sales.orders o
        where o.user_id = u.id and o.status = 'open'
        """,
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("sales", "orders", "user_id")].is_condition
    assert cols[("sales", "orders", "status")].is_condition


def test_schema_qualified_without_alias():
    parsed = parse_postgres_query(
        "select sales.orders.id from sales.orders where sales.orders.status = 'paid'",
        metadata(),
    )
    cols = columns(parsed)
    assert cols[("sales", "orders", "id")].is_selected
    assert cols[("sales", "orders", "status")].is_condition


def test_insert_into_simple_values():
    parsed = parse_postgres_query(
        "INSERT INTO public.users (name, email) VALUES ('Alice', 'alice@example.com')",
        metadata(),
    )
    tbls = tables(parsed)
    assert ("public", "users") in tbls


def test_insert_into_with_returning():
    parsed = parse_postgres_query(
        "INSERT INTO sales.orders (user_id, total) VALUES (1, 99.9) RETURNING id, status",
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("sales", "orders") in tbls
    assert cols[("sales", "orders", "id")].is_selected
    assert cols[("sales", "orders", "status")].is_selected


def test_insert_select_from_another_table():
    parsed = parse_postgres_query(
        "INSERT INTO sales.orders (user_id, total) SELECT u.id, 50.0 FROM public.users u WHERE u.email = 'x@y.com'",
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("sales", "orders") in tbls
    assert ("public", "users") in tbls
    assert cols[("public", "users", "id")].is_selected
    assert cols[("public", "users", "email")].is_condition


def test_update_simple_where():
    parsed = parse_postgres_query(
        "UPDATE public.users SET name = 'Johnny' WHERE id = 1",
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("public", "users") in tbls
    assert cols[("public", "users", "id")].is_condition


def test_update_with_from_join():
    parsed = parse_postgres_query(
        "UPDATE sales.orders o SET status = 'shipped' FROM public.users u WHERE o.user_id = u.id AND u.email LIKE '%@ship.com'",
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("sales", "orders") in tbls
    assert ("public", "users") in tbls
    assert cols[("sales", "orders", "user_id")].is_condition
    assert cols[("public", "users", "email")].is_condition


def test_update_with_subquery():
    parsed = parse_postgres_query(
        "UPDATE sales.orders SET total = total + 10 WHERE user_id IN (SELECT id FROM public.users WHERE email IS NOT NULL)",
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("sales", "orders") in tbls
    assert ("public", "users") in tbls
    assert cols[("public", "users", "email")].is_condition


def test_delete_simple():
    parsed = parse_postgres_query(
        "DELETE FROM public.users WHERE id = 5",
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("public", "users") in tbls
    assert cols[("public", "users", "id")].is_condition


def test_delete_with_using_join():
    parsed = parse_postgres_query(
        "DELETE FROM sales.order_items oi USING sales.orders o WHERE oi.order_id = o.id AND o.status = 'cancelled'",
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("sales", "order_items") in tbls
    assert ("sales", "orders") in tbls
    assert cols[("sales", "orders", "status")].is_condition


def test_vacuum_and_analyze():
    parsed_vac = parse_postgres_query("VACUUM ANALYZE public.users", metadata())
    parsed_vac_opts = parse_postgres_query("VACUUM (FULL, VERBOSE) sales.orders", metadata())
    parsed_ana = parse_postgres_query("ANALYZE inventory.products", metadata())
    assert ("public", "users") in tables(parsed_vac)
    assert ("sales", "orders") in tables(parsed_vac_opts)
    assert ("inventory", "products") in tables(parsed_ana)


def test_truncate_multiple_tables():
    parsed = parse_postgres_query("TRUNCATE TABLE sales.order_items, sales.orders RESTART IDENTITY", metadata())
    tbls = tables(parsed)
    assert ("sales", "order_items") in tbls
    assert ("sales", "orders") in tbls


def test_insert_with_cte_and_returning():
    parsed = parse_postgres_query(
        """
        WITH new_user AS (
            INSERT INTO public.users (name, email) VALUES ('Jane', 'jane@example.com') RETURNING id
        )
        INSERT INTO sales.orders (user_id, total) SELECT id, 100.0 FROM new_user
        """,
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("public", "users") in tbls
    assert ("sales", "orders") in tbls
    assert cols[("public", "users", "id")].is_selected


def test_update_with_multiple_tables_in_from_clause():
    parsed = parse_postgres_query(
        """
        UPDATE sales.order_items oi
        SET qty = oi.qty + 1
        FROM sales.orders o, public.users u
        WHERE oi.order_id = o.id AND o.user_id = u.id AND u.email = 'boss@corp.com'
        """,
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("sales", "order_items") in tbls
    assert ("sales", "orders") in tbls
    assert ("public", "users") in tbls
    assert cols[("public", "users", "email")].is_condition


def test_delete_with_exists_subquery():
    parsed = parse_postgres_query(
        """
        DELETE FROM public.users u
        WHERE EXISTS (
            SELECT 1 FROM sales.orders o WHERE o.user_id = u.id AND o.status = 'fraud'
        )
        """,
        metadata(),
    )
    tbls = tables(parsed)
    cols = columns(parsed)
    assert ("public", "users") in tbls
    assert ("sales", "orders") in tbls
    assert cols[("sales", "orders", "status")].is_condition


