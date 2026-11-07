"""Deterministic synthetic tenant for evals and offline demos: Metrika-like visits and hits for one counter and
amoCRM-like lead versions for one account over 60 days, the daily marts built from them with the platform's mart
logic, and a read-only `mapping.duckdb` whose dds.* / mart.* views read the local Parquet files (on the platform the
same views read Iceberg on S3). The other catalog tables are left out of the fixture (their views are absent).

All values are synthetic (example.com-style site, generic cities, made-up ids and hashes): no personal data.

    uv run python -m samovar_dev.tenant_fixture ../evals/.fixture
"""

import hashlib
import json
import random
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from samovar_agent.adapters.fixture_session import MAPPING_FILE
from samovar_agent.domain.catalog import Catalog, Table
from samovar_agent.engine.queries import load_sql_files
from samovar_agent.engine.sql_template import Identifier, Literal, LiteralStruct, render

SEED = 20261022
COUNTER = "90000001"
FIRST_DAY = date(2026, 8, 23)
DAYS = 60
SITE = "https://teapots.example"
RUN_ID = "fixture"
CONNECTOR_VERSION = 6
CAMPAIGN_START = date(2026, 10, 10)
CATALOG = Path(__file__).resolve().parents[3] / "spec" / "examples" / "catalog.demo.json"
ACCOUNT = "30000001"
PIPELINE = 6100001
FIRST_STAGE = 61000011
WON, LOST = 142, 143  # amoCRM's fixed ids of the closed stages
PRICES = [4500, 7900, 12500, 18900, 32000]

PAGES = {
    "/": "Чайники и самовары — магазин",
    "/catalog/teapots": "Чайники",
    "/catalog/samovars": "Самовары",
    "/catalog/cups": "Чашки",
    "/product/samovar-tula-5l": "Самовар тульский 5 л",
    "/product/teapot-glass": "Стеклянный чайник",
    "/blog/how-to-brew": "Как заваривать чай",
    "/cart": "Корзина",
    "/checkout": "Оформление заказа",
    "/contacts": "Контакты",
}
SOURCES = [
    ("organic", 40),
    ("direct", 25),
    ("ad", 15),
    ("referral", 8),
    ("social", 7),
    ("internal", 5),
]
DEVICES = [(1, 45), (2, 50), (3, 5)]
CITIES = [
    ("Россия", "Москва", 35),
    ("Россия", "Санкт-Петербург", 20),
    ("Россия", "Казань", 10),
    ("Россия", "Тула", 10),
    ("Россия", "Екатеринбург", 10),
    ("Казахстан", "Алматы", 5),
    ("Беларусь", "Минск", 10),
]
GOAL_CART, GOAL_CHECKOUT = 1001, 1002


@dataclass(frozen=True)
class DevQueries:
    json_to_parquet: str
    traffic_daily: str
    pages_daily: str
    leads_daily: str
    create_schema: str
    create_view: str


def pick(rng: random.Random, weighted: list[tuple[Any, int]]) -> Any:
    return rng.choices([item for item, _ in weighted], weights=[weight for _, weight in weighted])[0]


def attribution(rng: random.Random, source: str, day: date) -> dict[str, Any]:
    utm: dict[str, str | None] = {
        "utm_source": "",
        "utm_medium": "",
        "utm_campaign": "",
        "utm_content": "",
        "utm_term": "",
    }
    extra: dict[str, str | None] = {
        "adv_engine": None,
        "search_engine_root": None,
        "social_network": None,
        "referer": None,
    }
    if source == "ad":
        campaign = "autumn_sale" if day >= CAMPAIGN_START and rng.random() < 0.7 else "brand"
        engine = pick(rng, [("yandex", 70), ("vk", 30)])
        utm.update(
            utm_source=engine,
            utm_medium="cpc",
            utm_campaign=campaign,
            utm_content=f"ad{rng.randint(1, 3)}",
        )
        extra.update(adv_engine="Яндекс: Директ" if engine == "yandex" else "VK Реклама")
    elif source == "organic":
        extra.update(search_engine_root=pick(rng, [("Яндекс", 75), ("Google", 25)]))
    elif source == "social":
        network = pick(rng, [("vkontakte", 70), ("telegram", 30)])
        extra.update(social_network=network)
        utm.update(utm_source=network, utm_medium="social", utm_campaign="posts")
    elif source == "referral":
        extra.update(referer="https://tea-forum.example/thread/1")
    return {**utm, **extra}


def visits_and_hits(
    rng: random.Random,
) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    serial = 0
    for offset in range(DAYS):
        day = FIRST_DAY + timedelta(days=offset)
        weekend = day.weekday() >= 5
        boost = 1.3 if day >= CAMPAIGN_START else 1.0
        count = int((90 if weekend else 140) * boost) + rng.randint(0, 30)
        for _ in range(count):
            serial += 1
            yield visit(rng, day, serial)


def visit(rng: random.Random, day: date, serial: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source = pick(rng, SOURCES)
    device = pick(rng, DEVICES)
    country, city = pick(rng, [((c, t), w) for c, t, w in CITIES])
    started = datetime(day.year, day.month, day.day) + timedelta(seconds=rng.randint(0, 86_399))
    views = 1 if rng.random() < 0.35 else rng.randint(2, 8)
    duration = rng.randint(0, 14) if views == 1 else rng.randint(30, 900)
    paths = [rng.choice(list(PAGES)) for _ in range(views)]
    if views >= 4 and rng.random() < 0.5:
        paths[-2:] = ["/cart", "/checkout"] if rng.random() < 0.4 else [paths[-2], "/cart"]
    goals = [GOAL_CART for path in paths if path == "/cart"] + [GOAL_CHECKOUT for path in paths if path == "/checkout"]
    visit_id = str(7311864928374650000 + serial)
    marks = attribution(rng, source, day)
    common = {
        "counter_id": COUNTER,
        "traffic_source": source,
        "device_category": device,
        "operating_system_root": pick(rng, [("Android", 40), ("iOS", 20), ("Windows", 30), ("macOS", 10)]),
        "browser": pick(
            rng,
            [("Яндекс Браузер", 45), ("Chrome", 35), ("Safari", 15), ("Firefox", 5)],
        ),
        "region_country": country,
        "region_city": city,
        "_run_id": RUN_ID,
        "_connector_version_id": CONNECTOR_VERSION,
        **{
            key: marks[key]
            for key in (
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_content",
                "utm_term",
            )
        },
    }
    step = duration // max(views, 1)
    times = [started + timedelta(seconds=step * index) for index in range(views)]
    hits = [
        {
            **common,
            "watch_id": str(9045512837726100000 + serial * 16 + index),
            "page_view_id": str(1847729100000 + serial * 16 + index),
            "visit_id": visit_id,
            "occurred_at": moment.isoformat(sep=" "),
            "dt": moment.date().isoformat(),
            "title": PAGES[path],
            "url": SITE + path + ("?utm_source=" + common["utm_source"] if index == 0 and common["utm_source"] else ""),
            "referer": marks["referer"] if index == 0 else SITE + paths[index - 1],
            "page_views": 1,
            "link_clicks": 0,
            "downloads": 0,
            "not_bounce": 0 if views == 1 else 1,
            "artificial": 0,
            "http_error": None,
            "goals_id": ([GOAL_CART] if path == "/cart" else [GOAL_CHECKOUT] if path == "/checkout" else []),
            "goal_reaches": 1 if path in ("/cart", "/checkout") else 0,
        }
        for index, (path, moment) in enumerate(zip(paths, times))
    ]
    record = {
        **common,
        "visit_id": visit_id,
        "visit_year": day.year,
        "started_at": started.isoformat(sep=" "),
        "dt": day.isoformat(),
        "is_new_user": 1 if rng.random() < 0.6 else 0,
        "start_url": SITE + paths[0],
        "end_url": SITE + paths[-1],
        "page_views": views,
        "visit_duration": duration,
        "bounce": 1 if views == 1 and duration < 15 else 0,
        "goals_id": goals,
        "goals_date_time": [times[-1].isoformat(sep=" ")] * len(goals),
        "goal_reaches": len(goals),
        "adv_engine": marks["adv_engine"],
        "search_engine_root": marks["search_engine_root"],
        "social_network": marks["social_network"],
        "referer": marks["referer"],
        "browser_language": "ru",
        "attribution_model": "lastsign",
    }
    return record, hits


def lead_versions(rng: random.Random) -> Iterator[dict[str, Any]]:
    """Leads created from the site's campaigns: a first version on the day they come in, and for some of them a
    later version that closes them won or lost (one row per version, dt = the day of updated_at)."""
    managers = [hashlib.sha256(f"fixture-manager-{n}".encode()).hexdigest() for n in range(3)]
    last_day = FIRST_DAY + timedelta(days=DAYS - 1)
    serial = 0
    for offset in range(DAYS):
        day = FIRST_DAY + timedelta(days=offset)
        for _ in range(rng.randint(2, 5)):
            serial += 1
            source = pick(rng, [("ad", 40), ("organic", 35), ("social", 15), ("direct", 10)])
            marks = attribution(rng, source, day)
            created = datetime(day.year, day.month, day.day) + timedelta(seconds=rng.randint(28_800, 72_000))
            lead = {
                "lead_id": 20_000_000 + serial,
                "price": rng.choice(PRICES),
                "responsible_user_hash": rng.choice(managers),
                "created_at": created,
                "ym_counter_id": int(COUNTER),
                **{key: marks[key] or None for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content")},
            }
            yield lead_row(lead, FIRST_STAGE, created, None)
            if rng.random() < 0.6:
                closed = created + timedelta(days=rng.randint(1, 6), hours=rng.randint(0, 3))
                if closed.date() <= last_day:
                    yield lead_row(lead, WON if rng.random() < 0.5 else LOST, closed, closed)


def lead_row(lead: dict[str, Any], status: int, updated: datetime, closed: datetime | None) -> dict[str, Any]:
    stamp = updated.isoformat(sep=" ")
    return {
        "account_id": ACCOUNT,
        "lead_id": lead["lead_id"],
        "pipeline_id": PIPELINE,
        "status_id": status,
        "price": lead["price"],
        "responsible_user_hash": lead["responsible_user_hash"],
        "group_id": 0,
        "created_by_hash": lead["responsible_user_hash"],
        "updated_by_hash": lead["responsible_user_hash"],
        "created_at": lead["created_at"].isoformat(sep=" "),
        "updated_at": stamp,
        "closed_at": closed.isoformat(sep=" ") if closed else None,
        "closest_task_at": None,
        "is_deleted": False,
        "loss_reason_id": None,
        "source_id": None,
        "score": None,
        "labor_cost": None,
        "company_id": None,
        "contacts_count": 0,
        "contact_ids": [],
        "main_contact_id": None,
        "tag_ids": [],
        "tag_names": [],
        "ym_client_id_hash": None,
        "ym_counter_id": lead["ym_counter_id"],
        "utm_source": lead["utm_source"],
        "utm_medium": lead["utm_medium"],
        "utm_campaign": lead["utm_campaign"],
        "utm_content": lead["utm_content"],
        "utm_term": None,
        "referrer": None,
        "yclid_hash": None,
        "gclid_hash": None,
        "_version_at": stamp,
        "_run_id": RUN_ID,
        "_connector_version_id": 1,
        "dt": updated.date().isoformat(),
    }


def write_ndjson(path: Path, rows: list[dict[str, Any]], table: Table) -> None:
    names = [column.name for column in table.fields]
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            if set(row) != set(names):
                raise ValueError(f"{table.id}: fixture columns differ from the catalog: {set(row) ^ set(names)}")
            handle.write(json.dumps({name: row[name] for name in names}, ensure_ascii=False) + "\n")


def build_fixture(out: Path, catalog: Catalog) -> Path:
    queries = load_sql_files(DevQueries, "samovar_dev")
    rng = random.Random(SEED)
    visits: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    for record, events in visits_and_hits(rng):
        visits.append(record)
        hits.extend(events)
    detail = {"visits": visits, "hits": hits, "amocrm_leads": list(lead_versions(random.Random(SEED + 1)))}
    # mart id -> (the detail table it is built from, its SQL)
    marts = {
        "traffic_daily": ("visits", queries.traffic_daily),
        "pages_daily": ("hits", queries.pages_daily),
        "amocrm_leads_daily": ("amocrm_leads", queries.leads_daily),
    }
    tables = {table.id: table for table in catalog.tables if table.id in detail or table.id in marts}
    out.mkdir(parents=True, exist_ok=True)
    parquet = {name: out / table.layer.value / f"{name}.parquet" for name, table in tables.items()}
    for path in parquet.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(
        ":memory:",
        config={
            "autoinstall_known_extensions": False,
            "autoload_known_extensions": False,
        },
    ) as conn:
        for name, rows in detail.items():
            source = out / f"{name}.ndjson"
            write_ndjson(source, rows, tables[name])
            columns = LiteralStruct(tuple((column.name, column.type) for column in tables[name].fields))
            conn.execute(
                render(
                    queries.json_to_parquet,
                    {
                        "source": Literal(str(source)),
                        "columns": columns,
                        "target": Literal(str(parquet[name])),
                    },
                )
            )
        for name, (source_name, query) in marts.items():
            conn.execute(
                render(query, {"source": Literal(str(parquet[source_name])), "target": Literal(str(parquet[name]))})
            )
    mapping = out / MAPPING_FILE
    if mapping.exists():
        mapping.unlink()
    with duckdb.connect(str(mapping)) as conn:
        for schema in sorted({table.layer.value for table in tables.values()}):
            conn.execute(render(queries.create_schema, {"schema": Identifier(schema)}))
        for name, table in tables.items():
            schema, view = table.view.split(".", 1)
            conn.execute(
                render(
                    queries.create_view,
                    {
                        "schema": Identifier(schema),
                        "name": Identifier(view),
                        "path": Literal(str(parquet[name])),
                    },
                )
            )
    return mapping


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: tenant_fixture <output dir>", file=sys.stderr)
        return 2
    catalog = Catalog.model_validate_json(CATALOG.read_bytes())
    mapping = build_fixture(Path(argv[0]).resolve(), catalog)
    print(f"fixture tenant: {mapping}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
