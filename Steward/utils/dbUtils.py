import logging

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.engine import Result,Row 
from sqlalchemy.sql import Insert, Update, Delete
from typing import Optional, Union

from sqlalchemy import FromClause, TableClause

from Steward.models.objects.enum import QueryResultType

log = logging.getLogger(__name__)

async def execute_query(db: AsyncEngine, query: Union[FromClause, TableClause], result_type: QueryResultType = QueryResultType.single) -> Optional[Union[Row, list[Row]]]:
    write = isinstance(query, (Insert, Update, Delete))

    try:
        query_str = str(query)
    except Exception:
        query_str= repr(query)

    try:
        query_params = query.compile().params
    except Exception:
        query_params = None

    try:
        async with (db.begin() if write else db.connect()) as conn:
            results: Result = await conn.execute(query)
    except Exception as e:
        if write:
            log.error(
                "db.write.error query=%s params=%s error=%s",
                query_str,
                query_params,
                e
            )
        raise

    if write:
        log.info(
            "db.write.success query=%s params=%s",
            query_str,
            query_params
        )

    match result_type:
        case QueryResultType.single:
            return results.first()
        case QueryResultType.multiple:
            return results.fetchall()
        case QueryResultType.scalar:
            return results.scalar()
        
    return None