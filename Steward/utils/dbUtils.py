from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.engine import Result,Row 
from sqlalchemy.sql import Insert, Update, Delete
from typing import Optional, Union

from sqlalchemy import FromClause, TableClause

from Steward.models.objects.enum import QueryResultType


async def execute_query(db: AsyncEngine, query: Union[FromClause, TableClause], result_type: QueryResultType = QueryResultType.single) -> Optional[Union[Row, list[Row]]]:
    write = isinstance(query, (Insert, Update, Delete))

    async with (db.begin() if write else db.connect()) as conn:
        results: Result = await conn.execute(query)

    match result_type:
        case QueryResultType.single:
            return results.first()
        case QueryResultType.multiple:
            return results.fetchall()
        case QueryResultType.scalar:
            return results.scalar()
        
    return None