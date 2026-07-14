"""SQLAlchemy 2.x engine, session, and ORM models for the cache.

Times are stored as Julian Day (UT) floats — the native currency of Swiss
Ephemeris — and rendered into a city's local timezone only at read time.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    delete,
    update,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # CSC source id
    name: Mapped[str] = mapped_column(String, index=True)
    name_lower: Mapped[str] = mapped_column(String, index=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    tz: Mapped[str] = mapped_column(String)  # derived via timezonefinder at insert
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String, default="CSC")
    # Cache horizon actually computed for this city (ISO dates).
    cached_from: Mapped[str | None] = mapped_column(String, nullable=True)
    cached_to: Mapped[str | None] = mapped_column(String, nullable=True)


class CityDay(Base):
    __tablename__ = "city_days"
    __table_args__ = (UniqueConstraint("city_id", "date", name="uq_city_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    date: Mapped[str] = mapped_column(String, index=True)  # ISO yyyy-mm-dd
    sunrise_jd: Mapped[float | None] = mapped_column(Float, nullable=True)
    sunset_jd: Mapped[float | None] = mapped_column(Float, nullable=True)
    moonrise_jd: Mapped[float | None] = mapped_column(Float, nullable=True)
    moonset_jd: Mapped[float | None] = mapped_column(Float, nullable=True)


class GlobalEvent(Base):
    """A location-independent element boundary (its end instant, in UT JD)."""

    __tablename__ = "global_events"
    __table_args__ = (
        Index("ix_global_events_type_jd", "event_type", "end_jd"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String)  # tithi/nakshatra/yoga/karana/moon_rashi/sun_rashi
    idx: Mapped[int] = mapped_column(Integer)  # unreduced 0-based index of the element that ends
    end_jd: Mapped[float] = mapped_column(Float)


class GlobalEclipse(Base):
    __tablename__ = "global_eclipses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String)  # solar / lunar
    type: Mapped[str] = mapped_column(String)  # total/annular/partial/penumbral/hybrid
    max_jd: Mapped[float] = mapped_column(Float, index=True)
    begin_jd: Mapped[float] = mapped_column(Float)
    end_jd: Mapped[float] = mapped_column(Float)


class Meta(Base):
    """Key/value bookkeeping (e.g. the global-events computed span, seed flag)."""

    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


# --- Engine / session -------------------------------------------------------
_settings = get_settings()
_settings.db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{_settings.db_path.as_posix()}",
    future=True,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_meta(session, key: str, default: str | None = None) -> str | None:
    row = session.get(Meta, key)
    return row.value if row else default


def set_meta(session, key: str, value: str) -> None:
    row = session.get(Meta, key)
    if row:
        row.value = value
    else:
        session.add(Meta(key=key, value=value))


# Bump this whenever a change alters computed instants (ayanamsa, root-finder,
# boundary definitions, ...). On mismatch the computed cache is rebuilt so no
# stale values from an older engine survive. Seeded cities are preserved.
#   v2: fix per-thread Lahiri ayanamsa (was leaking Fagan-Bradley on worker
#       threads, corrupting all absolute-longitude quantities).
ENGINE_VERSION = "2-lahiri-perthread"

_ENGINE_VERSION_KEY = "engine_version"


def ensure_engine_version(session) -> bool:
    """Rebuild the computed cache if the engine version changed.

    Returns True if a wipe happened. Clears global_events / global_eclipses /
    city_days and resets every city's cached horizon + the global span markers,
    so the next request recomputes everything with the current engine. The
    seeded ``cities`` rows (names, coords, tz) are kept.
    """
    if get_meta(session, _ENGINE_VERSION_KEY) == ENGINE_VERSION:
        return False
    session.execute(delete(GlobalEvent))
    session.execute(delete(GlobalEclipse))
    session.execute(delete(CityDay))
    session.execute(update(City).values(cached_from=None, cached_to=None))
    for key in ("global_from_jd", "global_to_jd"):
        row = session.get(Meta, key)
        if row is not None:
            session.delete(row)
    set_meta(session, _ENGINE_VERSION_KEY, ENGINE_VERSION)
    session.commit()
    return True
