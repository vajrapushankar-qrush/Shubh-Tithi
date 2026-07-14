"""Fuzzy/startswith city search with country disambiguation."""
from __future__ import annotations

from sqlalchemy import select

from app.db import City


def search_cities(session, q: str, country: str | None = None, limit: int = 25) -> list[City]:
    """Prefix-then-substring search, most-populous first.

    ``country`` may be an ISO2 code or a country-name fragment to disambiguate
    (e.g. "London" in GB vs CA vs US).
    """
    q_norm = q.strip().lower()
    if not q_norm:
        return []

    stmt = select(City)
    if country:
        c = country.strip().lower()
        if len(c) == 2:
            stmt = stmt.where(City.country_code == c.upper())
        else:
            stmt = stmt.where(City.country.ilike(f"%{c}%"))

    prefix = stmt.where(City.name_lower.like(f"{q_norm}%")).order_by(
        City.population.desc().nullslast()
    ).limit(limit)
    results = list(session.scalars(prefix))

    if len(results) < limit:
        seen = {r.id for r in results}
        contains = stmt.where(City.name_lower.like(f"%{q_norm}%")).order_by(
            City.population.desc().nullslast()
        ).limit(limit * 2)
        for r in session.scalars(contains):
            if r.id not in seen:
                results.append(r)
                seen.add(r.id)
            if len(results) >= limit:
                break
    return results[:limit]


def get_city(session, city_id: int) -> City | None:
    return session.get(City, city_id)
