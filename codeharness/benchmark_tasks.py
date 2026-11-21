"""Small, reproducible Python repositories with private acceptance checks."""

from dataclasses import dataclass
from textwrap import dedent, indent


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    files: dict[str, str]
    reference: dict[str, str]
    acceptance: str


def source(text: str) -> str:
    # Inline first lines share the eight-space indentation of the fixture block.
    if text and not text[0].isspace():
        text = "        " + text
    return dedent(text).strip() + "\n"


def task(id, prompt, files, reference, public, acceptance) -> Task:
    files = {name: source(text) for name, text in files.items()}
    files["tests/test_public.py"] = ("import unittest\n\nclass PublicTests(unittest.TestCase):\n"
        "    def test_requirement(self):\n" + indent(source(public), "        "))
    return Task(id, prompt, files, {name: source(text) for name, text in reference.items()}, source(acceptance))


TASKS = (
    task("discount", "修复购物车百分比折扣：20% 折扣应乘以 0.8，保持现有 checkout 接口。运行测试。", {
        "pricing.py": """def discount(total, rate):
            return total - rate""",
        "checkout.py": """from pricing import discount

        def total(prices, rate=0):
            return discount(sum(prices), rate)""",
    }, {"pricing.py": """def discount(total, rate):
            return total * (1 - rate)"""}, """
        from checkout import total
        self.assertAlmostEqual(total([100, 50], 0.2), 120)
    """, """
        from math import isclose
        from checkout import total
        assert isclose(total([100, 50], 0.2), 120)
        assert total([10, 20]) == 30
        assert total([20], 1) == 0
        assert total([], 0.3) == 0
    """),
    task("pagination", "修复目录分页：页码从 1 开始，先按名称升序排序再分页，越界返回空列表。保留接口。", {
        "paging.py": """def page(items, number, size):
            start = number * size
            return items[start:start + size]""",
        "catalog.py": """from paging import page

        def list_items(items, number, size):
            return page(sorted(items, reverse=True), number, size)""",
    }, {
        "paging.py": """def page(items, number, size):
            start = (number - 1) * size
            return items[start:start + size]""",
        "catalog.py": """from paging import page

        def list_items(items, number, size):
            return page(sorted(items), number, size)""",
    }, """
        from catalog import list_items
        self.assertEqual(list_items(['c', 'a', 'b'], 1, 2), ['a', 'b'])
    """, """
        from catalog import list_items
        from paging import page
        items = ['e', 'c', 'a', 'd', 'b']
        assert list_items(items, 1, 2) == ['a', 'b']
        assert list_items(items, 2, 2) == ['c', 'd']
        assert list_items(items, 3, 2) == ['e']
        assert list_items(items, 4, 2) == []
        assert page([1, 2, 3], 1, 1) == [1]
        assert items == ['e', 'c', 'a', 'd', 'b']
    """),
    task("inventory", "修复库存预订：允许恰好用完库存，非正数量或库存不足不得扣库存。place 返回 accepted 或 out_of_stock。", {
        "inventory.py": """def reserve(stock, item, qty):
            if stock.get(item, 0) <= qty:
                return False
            stock[item] -= qty
            return True""",
        "orders.py": """from inventory import reserve

        def place(stock, item, qty):
            reserve(stock, item, qty)
            return 'accepted'""",
    }, {
        "inventory.py": """def reserve(stock, item, qty):
            if qty <= 0 or stock.get(item, 0) < qty:
                return False
            stock[item] -= qty
            return True""",
        "orders.py": """from inventory import reserve

        def place(stock, item, qty):
            return 'accepted' if reserve(stock, item, qty) else 'out_of_stock'""",
    }, """
        from orders import place
        stock = {'book': 2}
        self.assertEqual(place(stock, 'book', 2), 'accepted')
        self.assertEqual(stock['book'], 0)
    """, """
        from orders import place
        stock = {'book': 4}
        assert place(stock, 'book', 1) == 'accepted' and stock['book'] == 3
        assert place(stock, 'book', 3) == 'accepted' and stock['book'] == 0
        assert place(stock, 'book', 1) == 'out_of_stock' and stock['book'] == 0
        assert place(stock, 'book', -3) == 'out_of_stock' and stock['book'] == 0
        assert place(stock, 'missing', 1) == 'out_of_stock' and 'missing' not in stock
    """),
    task("config", "修复配置合并：用户配置优先于默认值，保留未知字段及 False、0、空字符串，不修改传入字典。", {
        "config.py": """def merge(defaults, overrides):
            return {**overrides, **defaults}""",
        "service.py": """from config import merge
        DEFAULTS = {'retries': 3, 'debug': True, 'name': 'app'}

        def settings(overrides):
            return merge(DEFAULTS, {k: v for k, v in overrides.items() if v})""",
    }, {
        "config.py": """def merge(defaults, overrides):
            return {**defaults, **overrides}""",
        "service.py": """from config import merge
        DEFAULTS = {'retries': 3, 'debug': True, 'name': 'app'}

        def settings(overrides):
            return merge(DEFAULTS, overrides)""",
    }, """
        from service import settings
        self.assertEqual(settings({'retries': 1})['retries'], 1)
    """, """
        from service import settings, DEFAULTS
        from config import merge
        overrides = {'retries': 0, 'debug': False, 'name': '', 'port': 1234}
        assert settings(overrides) == overrides
        assert settings({}) == {'retries': 3, 'debug': True, 'name': 'app'}
        assert merge({'a': 1}, {'b': 2}) == {'a': 1, 'b': 2}
        assert DEFAULTS == {'retries': 3, 'debug': True, 'name': 'app'}
    """),
    task("invoice", "发票总价必须包含运费并使用 Decimal。保留 invoice.total 和 money.cents 接口，"
        "两个函数都使用 ROUND_HALF_UP 按分舍入，负金额也适用。", {
        "money.py": """from decimal import Decimal, ROUND_DOWN

        def cents(value):
            return value.quantize(Decimal('0.01'), rounding=ROUND_DOWN)""",
        "invoice.py": """from decimal import Decimal
        from money import cents

        def total(items, shipping=Decimal('0')):
            return cents(sum(items, Decimal('0')))""",
    }, {
        "money.py": """from decimal import Decimal, ROUND_HALF_UP

        def cents(value):
            return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)""",
        "invoice.py": """from decimal import Decimal
        from money import cents

        def total(items, shipping=Decimal('0')):
            return cents(sum(items, Decimal('0')) + shipping)""",
    }, """
        from decimal import Decimal as D
        from invoice import total
        self.assertEqual(total([D('1.235')], D('0.10')), D('1.34'))
    """, """
        from decimal import Decimal as D
        from invoice import total
        from money import cents
        assert total([D('1.235')], D('0.10')) == D('1.34')
        assert total([D('0.005'), D('0.005')]) == D('0.01')
        assert total([], D('2.50')) == D('2.50')
        assert cents(D('-1.235')) == D('-1.24')
    """),
    task("date-report", "日报筛选的开始和结束日期都应包含在结果中，保持输入记录的原始顺序。", {
        "dates.py": """def in_range(value, start, end):
            return start <= value < end""",
        "report.py": """from dates import in_range

        def select(records, start, end):
            return [r for r in records if in_range(r[0], start, end)]""",
    }, {"dates.py": """def in_range(value, start, end):
            return start <= value <= end"""}, """
        from report import select
        self.assertEqual(select([('2026-01-03', 1)], '2026-01-01', '2026-01-03'), [('2026-01-03', 1)])
    """, """
        from report import select
        rows = [('2026-01-03', 3), ('2026-01-01', 1), ('2026-01-04', 4), ('2026-01-02', 2)]
        assert select(rows, '2026-01-01', '2026-01-03') == [rows[0], rows[1], rows[3]]
        assert select(rows, '2026-01-02', '2026-01-02') == [rows[3]]
        assert select(rows, '2026-02-01', '2026-02-02') == []
    """),
    task("csv-import", "导入 CSV 库存：去掉商品名前后空白，忽略空白商品名，将同名商品数量累加。保持 load 接口。", {
        "parser.py": """import csv
        from io import StringIO

        def rows(text):
            return [(r['name'], int(r['quantity'])) for r in csv.DictReader(StringIO(text))]""",
        "importer.py": """from parser import rows

        def load(text):
            return dict(rows(text))""",
    }, {
        "parser.py": """import csv
        from io import StringIO

        def rows(text):
            return [(r['name'].strip(), int(r['quantity'])) for r in csv.DictReader(StringIO(text)) if r['name'].strip()]""",
        "importer.py": """from parser import rows

        def load(text):
            result = {}
            for name, qty in rows(text):
                result[name] = result.get(name, 0) + qty
            return result""",
    }, """
        from importer import load
        self.assertEqual(load('name,quantity\\n apple ,2\\napple,3\\n'), {'apple': 5})
    """, """
        from importer import load
        assert load('name,quantity\\n apple ,2\\napple,3\\n ,99\\npear,1\\n') == {'apple': 5, 'pear': 1}
        assert load('name,quantity\\n') == {}
        assert load('name,quantity\\n"tea, green",4\\n') == {'tea, green': 4}
    """),
    task("dedupe", "按订单 ID 去重：保留第一次出现的完整订单和原始顺序；报表仍返回金额列表。", {
        "orders.py": """def unique(orders):
            return list({o['id']: o for o in orders}.values())""",
        "report.py": """from orders import unique

        def amounts(orders):
            return [o['amount'] for o in unique(orders)]""",
    }, {"orders.py": """def unique(orders):
            seen = set()
            result = []
            for order in orders:
                if order['id'] not in seen:
                    seen.add(order['id'])
                    result.append(order)
            return result"""}, """
        from report import amounts
        self.assertEqual(amounts([{'id': 1, 'amount': 10}, {'id': 1, 'amount': 20}]), [10])
    """, """
        from report import amounts
        from orders import unique
        a = {'id': 2, 'amount': 5, 'note': 'first'}
        b = {'id': 1, 'amount': 7}
        orders = [a, b, {'id': 2, 'amount': 90}]
        assert unique(orders) == [a, b]
        assert amounts(orders) == [5, 7]
        assert amounts([]) == []
    """),
    task("backoff", "修复任务调度等待时间：第一次重试等待 base，逐次倍增，最多 cap 秒。保持 next_delay 接口。", {
        "delay.py": """def backoff(attempt, base, cap):
            return min(cap, base * 2 ** attempt)""",
        "scheduler.py": """from delay import backoff

        def next_delay(attempt, base=2, cap=20):
            return backoff(attempt, base, cap)""",
    }, {"delay.py": """def backoff(attempt, base, cap):
            return min(cap, base * 2 ** (attempt - 1))"""}, """
        from scheduler import next_delay
        self.assertEqual(next_delay(1), 2)
    """, """
        from scheduler import next_delay
        assert [next_delay(i) for i in range(1, 6)] == [2, 4, 8, 16, 20]
        assert next_delay(2, base=3, cap=5) == 5
        assert next_delay(1, base=3, cap=2) == 2
    """),
    task("catalog-search", "商品名称搜索忽略大小写及查询词首尾空白，空查询返回全部，保留输入顺序。", {
        "matcher.py": """def matches(query, title):
            return query in title""",
        "catalog.py": """from matcher import matches

        def search(products, query):
            return [p for p in products if matches(query, p)]""",
    }, {"matcher.py": """def matches(query, title):
            return query.strip().casefold() in title.casefold()"""}, """
        from catalog import search
        self.assertEqual(search(['Apple', 'pear'], ' apple '), ['Apple'])
    """, """
        from catalog import search
        products = ['Red APPLE', 'Pear', 'apple pie', 'Tea']
        assert search(products, ' APPLE ') == ['Red APPLE', 'apple pie']
        assert search(products, '  ') == products
        assert search(products, 'banana') == []
        assert search(['Straße'], 'STRASSE') == ['Straße']
    """),
    task("shipping", "购物车满 100 元含 100 免运费，否则运费 8 元；quote 返回商品金额加运费。", {
        "shipping.py": """def fee(subtotal):
            return 0 if subtotal > 100 else 8""",
        "cart.py": """from shipping import fee

        def quote(prices):
            subtotal = sum(prices)
            return subtotal""",
    }, {
        "shipping.py": """def fee(subtotal):
            return 0 if subtotal >= 100 else 8""",
        "cart.py": """from shipping import fee

        def quote(prices):
            subtotal = sum(prices)
            return subtotal + fee(subtotal)""",
    }, """
        from cart import quote
        self.assertEqual(quote([20, 30]), 58)
    """, """
        from cart import quote
        from shipping import fee
        assert quote([20, 30]) == 58
        assert quote([60, 40]) == 100
        assert quote([101]) == 101
        assert fee(99) == 8 and fee(100) == 0
    """),
    task("metrics", "指标报表将每组数值的平均值保留为浮点数；空组平均值为 0，不丢弃空组。", {
        "stats.py": """def mean(values):
            return sum(values) // len(values)""",
        "report.py": """from stats import mean

        def summary(groups):
            return {name: mean(values) for name, values in groups.items() if values}""",
    }, {
        "stats.py": """def mean(values):
            return sum(values) / len(values) if values else 0.0""",
        "report.py": """from stats import mean

        def summary(groups):
            return {name: mean(values) for name, values in groups.items()}""",
    }, """
        from report import summary
        self.assertEqual(summary({'a': [1, 2]}), {'a': 1.5})
    """, """
        from report import summary
        from stats import mean
        assert summary({'a': [1, 2], 'b': [], 'c': [-1, 0]}) == {'a': 1.5, 'b': 0.0, 'c': -0.5}
        assert isinstance(mean([2, 4]), float)
        assert summary({}) == {}
    """),
)


MULTI_TASKS = (
    task(
        "order-pipeline",
        "这是一个多模块订单结算系统，请先梳理各模块调用链，再修复以下问题并运行测试："
        "1）满减券达到阈值（含等于）即可生效，且折后金额不得低于 0；"
        "2）计税基数必须按扣除优惠券后的金额计算；"
        "3）提交订单时若库存不足，不得确认订单、不得记录 confirmed 审计事件，应返回 status='rejected'。",
        {
            "app/__init__.py": "",
            "app/models.py": """
                from dataclasses import dataclass

                @dataclass(frozen=True)
                class LineItem:
                    sku: str
                    unit_price: int
                    qty: int

                @dataclass(frozen=True)
                class Coupon:
                    code: str
                    threshold: int
                    amount: int
            """,
            "app/catalog.py": """
                def subtotal_cents(items):
                    return sum(item.unit_price * item.qty for item in items)
            """,
            "app/coupons.py": """
                def discount_cents(subtotal, coupon):
                    if coupon is None:
                        return 0
                    if subtotal > coupon.threshold:
                        return coupon.amount
                    return 0
            """,
            "app/tax.py": """
                def calculate_tax(subtotal, discount, rate_bps):
                    taxable = subtotal
                    return (taxable * rate_bps + 5000) // 10000
            """,
            "app/shipping.py": """
                def shipping_cents(net_subtotal):
                    if net_subtotal <= 0:
                        return 0
                    return 0 if net_subtotal >= 10000 else 800
            """,
            "app/inventory.py": """
                def reserve(stock, items):
                    for item in items:
                        if item.qty <= 0 or stock.get(item.sku, 0) < item.qty:
                            return False
                    for item in items:
                        stock[item.sku] -= item.qty
                    return True
            """,
            "app/audit.py": """
                def record(log, event, order_id, detail):
                    log.append({"event": event, "order_id": order_id, "detail": detail})
            """,
            "app/notifications.py": """
                def build_receipt(order):
                    return f"Order {order['order_id']}: {order['status']} total={order['total']}"
            """,
            "app/formatters.py": """
                def format_cents(cents):
                    return f"{cents / 100:.2f}"
            """,
            "app/pipeline.py": """
                from app.audit import record
                from app.catalog import subtotal_cents
                from app.coupons import discount_cents
                from app.inventory import reserve
                from app.shipping import shipping_cents
                from app.tax import calculate_tax

                def submit_order(order_id, items, stock, audit_log, coupon=None, tax_bps=1000):
                    subtotal = subtotal_cents(items)
                    discount = discount_cents(subtotal, coupon)
                    net = subtotal - discount
                    tax = calculate_tax(subtotal, discount, tax_bps)
                    shipping = shipping_cents(net)
                    reserve(stock, items)
                    order = {
                        "order_id": order_id,
                        "status": "confirmed",
                        "subtotal": subtotal,
                        "discount": discount,
                        "tax": tax,
                        "shipping": shipping,
                        "total": net + tax + shipping,
                    }
                    record(audit_log, "confirmed", order_id, order["total"])
                    return order
            """,
        },
        {
            "app/coupons.py": """
                def discount_cents(subtotal, coupon):
                    if coupon is None:
                        return 0
                    if subtotal >= coupon.threshold:
                        return min(subtotal, max(0, coupon.amount))
                    return 0
            """,
            "app/tax.py": """
                def calculate_tax(subtotal, discount, rate_bps):
                    taxable = max(0, subtotal - discount)
                    return (taxable * rate_bps + 5000) // 10000
            """,
            "app/pipeline.py": """
                from app.audit import record
                from app.catalog import subtotal_cents
                from app.coupons import discount_cents
                from app.inventory import reserve
                from app.shipping import shipping_cents
                from app.tax import calculate_tax

                def submit_order(order_id, items, stock, audit_log, coupon=None, tax_bps=1000):
                    subtotal = subtotal_cents(items)
                    discount = discount_cents(subtotal, coupon)
                    net = subtotal - discount
                    tax = calculate_tax(subtotal, discount, tax_bps)
                    shipping = shipping_cents(net)
                    if not reserve(stock, items):
                        record(audit_log, "rejected", order_id, "out_of_stock")
                        return {
                            "order_id": order_id,
                            "status": "rejected",
                            "subtotal": subtotal,
                            "discount": discount,
                            "tax": tax,
                            "shipping": shipping,
                            "total": 0,
                        }
                    order = {
                        "order_id": order_id,
                        "status": "confirmed",
                        "subtotal": subtotal,
                        "discount": discount,
                        "tax": tax,
                        "shipping": shipping,
                        "total": net + tax + shipping,
                    }
                    record(audit_log, "confirmed", order_id, order["total"])
                    return order
            """,
        },
        """
            from app.models import Coupon, LineItem
            from app.pipeline import submit_order
            log = []
            stock = {"sku1": 2}
            order = submit_order("O1", [LineItem("sku1", 5000, 1)], stock, log, Coupon("C50", 5000, 1000), tax_bps=1000)
            self.assertEqual(order["discount"], 1000)
            self.assertEqual(order["tax"], 400)
        """,
        """
            from app.models import Coupon, LineItem
            from app.pipeline import submit_order
            from app.coupons import discount_cents
            from app.tax import calculate_tax

            assert discount_cents(5000, Coupon("C", 5000, 1000)) == 1000
            assert discount_cents(500, Coupon("BIG", 500, 900)) == 500
            assert calculate_tax(5000, 1000, 1000) == 400

            log = []
            stock = {"sku1": 1}
            ok = submit_order("O1", [LineItem("sku1", 5000, 1)], stock, log, Coupon("C", 5000, 1000), tax_bps=1000)
            assert ok["status"] == "confirmed"
            assert ok["discount"] == 1000 and ok["tax"] == 400 and ok["shipping"] == 800 and ok["total"] == 5200
            assert stock["sku1"] == 0

            bad_log = []
            rejected = submit_order("O2", [LineItem("sku1", 5000, 1)], stock, bad_log, Coupon("C", 5000, 1000), tax_bps=1000)
            assert rejected["status"] == "rejected"
            assert stock["sku1"] == 0
            assert not any(entry["event"] == "confirmed" for entry in bad_log)

            free_log = []
            free_stock = {"sku2": 1}
            free = submit_order("O3", [LineItem("sku2", 500, 1)], free_stock, free_log, Coupon("FREE", 500, 1000), tax_bps=1000)
            assert free["status"] == "confirmed" and free["discount"] == 500 and free["tax"] == 0 and free["total"] == 0
        """,
    ),
    task(
        "rbac-gateway",
        "这是一个多租户后端权限网关，请先探索模块结构，修复以下鉴权缺陷并运行测试："
        "1）角色继承必须支持多层传递展开（且避免循环继承死循环）；"
        "2）权限策略判定时，显式 deny 规则永远优先于 allow 规则；"
        "3）跨租户请求（token.tenant_id != request.tenant_id）必须直接拒绝并记录审计拒绝事件。",
        {
            "app/__init__.py": "",
            "app/models.py": """
                from dataclasses import dataclass

                @dataclass(frozen=True)
                class Token:
                    subject: str
                    tenant_id: str
                    roles: tuple[str, ...]

                @dataclass(frozen=True)
                class Request:
                    tenant_id: str
                    resource: str
                    action: str

                @dataclass(frozen=True)
                class Rule:
                    role: str
                    resource: str
                    action: str
                    effect: str
            """,
            "app/roles.py": """
                def expand_roles(direct_roles, hierarchy):
                    result = set(direct_roles)
                    for role in list(direct_roles):
                        result.update(hierarchy.get(role, ()))
                    return result
            """,
            "app/policies.py": """
                def evaluate(roles, rules, resource, action):
                    decision = False
                    for rule in rules:
                        if rule.role in roles and rule.resource in {resource, "*"} and rule.action in {action, "*"}:
                            decision = rule.effect == "allow"
                    return decision
            """,
            "app/tokens.py": """
                def is_valid(token):
                    return bool(token and token.subject and token.tenant_id)
            """,
            "app/ratelimit.py": """
                def within_limit(counters, key, limit):
                    used = counters.get(key, 0)
                    if used >= limit:
                        return False
                    counters[key] = used + 1
                    return True
            """,
            "app/tenant.py": """
                def is_same_tenant(token, request):
                    return token.tenant_id == request.tenant_id
            """,
            "app/cache.py": """
                def cache_key(token, request):
                    return f"{token.tenant_id}:{token.subject}:{request.resource}:{request.action}"
            """,
            "app/audit.py": """
                def log_decision(events, subject, tenant_id, allowed, reason):
                    events.append({"subject": subject, "tenant_id": tenant_id, "allowed": allowed, "reason": reason})
            """,
            "app/metrics.py": """
                def count_decision(stats, allowed):
                    key = "allowed" if allowed else "denied"
                    stats[key] = stats.get(key, 0) + 1
            """,
            "app/gateway.py": """
                from app.audit import log_decision
                from app.metrics import count_decision
                from app.policies import evaluate
                from app.ratelimit import within_limit
                from app.roles import expand_roles
                from app.tokens import is_valid

                def authorize(token, request, hierarchy, rules, audit_events, rate_counters=None, limit=100, stats=None):
                    if not is_valid(token):
                        log_decision(audit_events, "", request.tenant_id, False, "invalid_token")
                        if stats is not None:
                            count_decision(stats, False)
                        return {"allowed": False, "reason": "invalid_token"}
                    if rate_counters is not None and not within_limit(rate_counters, token.subject, limit):
                        log_decision(audit_events, token.subject, request.tenant_id, False, "rate_limited")
                        if stats is not None:
                            count_decision(stats, False)
                        return {"allowed": False, "reason": "rate_limited"}
                    effective = expand_roles(token.roles, hierarchy)
                    allowed = evaluate(effective, rules, request.resource, request.action)
                    reason = "allowed" if allowed else "policy_denied"
                    log_decision(audit_events, token.subject, request.tenant_id, allowed, reason)
                    if stats is not None:
                        count_decision(stats, allowed)
                    return {"allowed": allowed, "reason": reason}
            """,
        },
        {
            "app/roles.py": """
                def expand_roles(direct_roles, hierarchy):
                    result = set()
                    stack = list(direct_roles)
                    while stack:
                        role = stack.pop()
                        if role in result:
                            continue
                        result.add(role)
                        stack.extend(hierarchy.get(role, ()))
                    return result
            """,
            "app/policies.py": """
                def evaluate(roles, rules, resource, action):
                    allowed = False
                    for rule in rules:
                        if rule.role in roles and rule.resource in {resource, "*"} and rule.action in {action, "*"}:
                            if rule.effect == "deny":
                                return False
                            if rule.effect == "allow":
                                allowed = True
                    return allowed
            """,
            "app/gateway.py": """
                from app.audit import log_decision
                from app.metrics import count_decision
                from app.policies import evaluate
                from app.ratelimit import within_limit
                from app.roles import expand_roles
                from app.tenant import is_same_tenant
                from app.tokens import is_valid

                def authorize(token, request, hierarchy, rules, audit_events, rate_counters=None, limit=100, stats=None):
                    if not is_valid(token):
                        log_decision(audit_events, "", request.tenant_id, False, "invalid_token")
                        if stats is not None:
                            count_decision(stats, False)
                        return {"allowed": False, "reason": "invalid_token"}
                    if not is_same_tenant(token, request):
                        log_decision(audit_events, token.subject, request.tenant_id, False, "tenant_mismatch")
                        if stats is not None:
                            count_decision(stats, False)
                        return {"allowed": False, "reason": "tenant_mismatch"}
                    if rate_counters is not None and not within_limit(rate_counters, token.subject, limit):
                        log_decision(audit_events, token.subject, request.tenant_id, False, "rate_limited")
                        if stats is not None:
                            count_decision(stats, False)
                        return {"allowed": False, "reason": "rate_limited"}
                    effective = expand_roles(token.roles, hierarchy)
                    allowed = evaluate(effective, rules, request.resource, request.action)
                    reason = "allowed" if allowed else "policy_denied"
                    log_decision(audit_events, token.subject, request.tenant_id, allowed, reason)
                    if stats is not None:
                        count_decision(stats, allowed)
                    return {"allowed": allowed, "reason": reason}
            """,
        },
        """
            from app.gateway import authorize
            from app.models import Request, Rule, Token
            hierarchy = {"admin": ("editor",), "editor": ("viewer",)}
            rules = [Rule("viewer", "docs", "read", "allow")]
            events = []
            res = authorize(Token("u1", "t1", ("admin",)), Request("t1", "docs", "read"), hierarchy, rules, events)
            self.assertTrue(res["allowed"])
        """,
        """
            from app.gateway import authorize
            from app.models import Request, Rule, Token
            from app.roles import expand_roles

            hierarchy = {"admin": ("editor",), "editor": ("viewer",), "viewer": ("admin",)}
            assert expand_roles(("admin",), hierarchy) == {"admin", "editor", "viewer"}

            rules = [
                Rule("editor", "secrets", "read", "deny"),
                Rule("admin", "*", "*", "allow"),
            ]
            events = []
            denied = authorize(Token("u1", "t1", ("admin",)), Request("t1", "secrets", "read"), hierarchy, rules, events)
            assert not denied["allowed"]

            ok_events = []
            allowed = authorize(Token("u1", "t1", ("admin",)), Request("t1", "docs", "read"), hierarchy, rules, ok_events)
            assert allowed["allowed"]

            cross_events = []
            cross = authorize(Token("u1", "t1", ("admin",)), Request("t2", "docs", "read"), hierarchy, rules, cross_events)
            assert not cross["allowed"]
            assert len(cross_events) == 1 and not cross_events[0]["allowed"]
        """,
    ),
    task(
        "ledger-reconcile",
        "这是一个多模块财务记账与对账引擎，请先梳理模块依赖并修复以下问题，运行测试验证："
        "1）记账校验必须拒绝非正金额分录且确保借方总额等于贷方总额；"
        "2）相同 idempotency_key 重复入账必须幂等返回原凭证且不得重复修改账户余额；"
        "3）对账差异必须同时报告账本缺失（missing_in_ledger）和金额不符（amount_mismatch）以及外部缺失（missing_in_external），并按 ref 升序排列。",
        {
            "app/__init__.py": "",
            "app/currency.py": """
                def to_cents(amount):
                    return int(round(amount * 100))
            """,
            "app/accounts.py": """
                def ensure_account(balances, account):
                    balances.setdefault(account, 0)
            """,
            "app/entries.py": """
                from dataclasses import dataclass

                @dataclass(frozen=True)
                class Entry:
                    account: str
                    side: str
                    amount: int
            """,
            "app/validators.py": """
                def validate_voucher(entries):
                    if not entries:
                        raise ValueError("empty voucher")
                    debit = sum(e.amount for e in entries if e.side == "debit")
                    credit = sum(e.amount for e in entries if e.side == "credit")
                    if debit != credit:
                        raise ValueError("unbalanced voucher")
            """,
            "app/balances.py": """
                from app.accounts import ensure_account

                def apply_entries(balances, entries):
                    for entry in entries:
                        ensure_account(balances, entry.account)
                        delta = entry.amount if entry.side == "debit" else -entry.amount
                        balances[entry.account] += delta
            """,
            "app/posting.py": """
                from app.balances import apply_entries
                from app.validators import validate_voucher

                class Ledger:
                    def __init__(self):
                        self.balances = {}
                        self.vouchers = {}
                        self.by_key = {}
                        self.external_totals = {}

                    def post(self, ref, entries, idempotency_key=None):
                        validate_voucher(entries)
                        apply_entries(self.balances, entries)
                        amount = sum(e.amount for e in entries if e.side == "debit")
                        voucher = {"ref": ref, "amount": amount, "entries": list(entries)}
                        self.vouchers[ref] = voucher
                        if idempotency_key is not None:
                            self.by_key[idempotency_key] = voucher
                        return voucher
            """,
            "app/reconcile.py": """
                def reconcile(vouchers, external_records):
                    diffs = []
                    ext_map = {row["ref"]: row["amount"] for row in external_records}
                    for ref, voucher in vouchers.items():
                        if ref not in ext_map:
                            diffs.append({"ref": ref, "kind": "missing_in_external"})
                        elif ext_map[ref] != voucher["amount"]:
                            diffs.append({"ref": ref, "kind": "amount_mismatch"})
                    return diffs
            """,
            "app/export.py": """
                def to_rows(vouchers):
                    return [(ref, data["amount"]) for ref, data in sorted(vouchers.items())]
            """,
            "app/statements.py": """
                def trial_balance(balances):
                    return sum(balances.values())
            """,
            "app/cli_view.py": """
                def format_diffs(diffs):
                    return [f"{d['ref']}:{d['kind']}" for d in diffs]
            """,
        },
        {
            "app/validators.py": """
                def validate_voucher(entries):
                    if not entries:
                        raise ValueError("empty voucher")
                    for entry in entries:
                        if entry.side not in {"debit", "credit"} or entry.amount <= 0:
                            raise ValueError("invalid entry")
                    debit = sum(e.amount for e in entries if e.side == "debit")
                    credit = sum(e.amount for e in entries if e.side == "credit")
                    if debit != credit:
                        raise ValueError("unbalanced voucher")
            """,
            "app/posting.py": """
                from app.balances import apply_entries
                from app.validators import validate_voucher

                class Ledger:
                    def __init__(self):
                        self.balances = {}
                        self.vouchers = {}
                        self.by_key = {}
                        self.external_totals = {}

                    def post(self, ref, entries, idempotency_key=None):
                        if idempotency_key is not None and idempotency_key in self.by_key:
                            return self.by_key[idempotency_key]
                        validate_voucher(entries)
                        apply_entries(self.balances, entries)
                        amount = sum(e.amount for e in entries if e.side == "debit")
                        voucher = {"ref": ref, "amount": amount, "entries": list(entries)}
                        self.vouchers[ref] = voucher
                        if idempotency_key is not None:
                            self.by_key[idempotency_key] = voucher
                        return voucher
            """,
            "app/reconcile.py": """
                def reconcile(vouchers, external_records):
                    diffs = []
                    ext_map = {row["ref"]: row["amount"] for row in external_records}
                    for ref in sorted(vouchers.keys() | ext_map.keys()):
                        if ref not in ext_map:
                            diffs.append({"ref": ref, "kind": "missing_in_external"})
                        elif ref not in vouchers:
                            diffs.append({"ref": ref, "kind": "missing_in_ledger"})
                        elif ext_map[ref] != vouchers[ref]["amount"]:
                            diffs.append({"ref": ref, "kind": "amount_mismatch"})
                    return diffs
            """,
        },
        """
            from app.entries import Entry
            from app.posting import Ledger
            ledger = Ledger()
            entries = [Entry("cash", "debit", 100), Entry("rev", "credit", 100)]
            first = ledger.post("V1", entries, idempotency_key="k1")
            second = ledger.post("V1-dup", entries, idempotency_key="k1")
            self.assertEqual(first["ref"], second["ref"])
            self.assertEqual(ledger.balances["cash"], 100)
        """,
        """
            from app.entries import Entry
            from app.posting import Ledger
            from app.reconcile import reconcile
            from app.statements import trial_balance

            ledger = Ledger()
            try:
                ledger.post("BAD", [Entry("cash", "debit", -10), Entry("rev", "credit", -10)])
                raise AssertionError("negative entry must fail")
            except ValueError:
                pass

            entries = [Entry("cash", "debit", 100), Entry("rev", "credit", 100)]
            v1 = ledger.post("V2", entries, idempotency_key="idem-1")
            v1_retry = ledger.post("V2-retry", entries, idempotency_key="idem-1")
            assert v1_retry["ref"] == "V2"
            assert ledger.balances == {"cash": 100, "rev": -100}
            assert trial_balance(ledger.balances) == 0

            ledger.post("V3", [Entry("cash", "debit", 50), Entry("rev", "credit", 50)])
            diffs = reconcile(ledger.vouchers, [{"ref": "V1", "amount": 20}, {"ref": "V2", "amount": 90}])
            assert diffs == [
                {"ref": "V1", "kind": "missing_in_ledger"},
                {"ref": "V2", "kind": "amount_mismatch"},
                {"ref": "V3", "kind": "missing_in_external"},
            ]
        """,
    ),
)

ALL_TASKS = TASKS + MULTI_TASKS
