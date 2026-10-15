from typing import Annotated

from fastapi import APIRouter, Body, Path, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from rentalab.auth.dependencies import CustomerUser
from rentalab.database import SQLITE_MAX_INTEGER, immediate_transaction
from rentalab.equipment.groups import active_product_units, product_key
from rentalab.equipment.models import Equipment
from rentalab.equipment.service import EquipmentNotFound
from rentalab.http import DatabaseSession, ErrorResponse
from rentalab.me.models import SavedProduct

router = APIRouter(prefix="/api/me/saved-products", tags=["Mis productos guardados"])
PositiveId = Annotated[int, Path(gt=0, le=SQLITE_MAX_INTEGER)]
ERROR_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Sesión ausente, caducada o desactivada"},
    403: {"model": ErrorResponse, "description": "Requiere rol cliente y CSRF en escrituras"},
    404: {"model": ErrorResponse, "description": "El producto que se intenta guardar no existe"},
    503: {"model": ErrorResponse, "description": "SQLite ocupada; reintento explícito posterior"},
}


class SavedProductsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equipment_ids: list[int]


class EmptyParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")


def saved_rows(session: Session, customer_user_id: int) -> list[tuple[SavedProduct, Equipment]]:
    return list(
        session.execute(
            select(SavedProduct, Equipment)
            .join(Equipment, SavedProduct.equipment_id == Equipment.id)
            .where(SavedProduct.customer_user_id == customer_user_id)
            .order_by(SavedProduct.equipment_id)
        ).tuples()
    )


def saved_product_ids(session: Session, customer_user_id: int) -> SavedProductsRead:
    # A model's public representative can change when an administrator archives a unit.
    # Keep the saved anchor intact, but return the current catalogue ID while available.
    # Entirely archived models retain an ID so their customer can still remove them.
    representatives: dict[tuple[str, str], int] = {}
    for item in session.scalars(
        select(Equipment).where(Equipment.active.is_(True)).order_by(Equipment.id)
    ):
        representatives.setdefault(product_key(item), item.id)
    products: dict[tuple[str, str], int] = {}
    for _saved, equipment in saved_rows(session, customer_user_id):
        key = product_key(equipment)
        products.setdefault(key, representatives.get(key, equipment.id))
    return SavedProductsRead(equipment_ids=sorted(products.values()))


@router.get(
    "",
    response_model=SavedProductsRead,
    responses=ERROR_RESPONSES,
    summary="Listar los productos guardados de mi cuenta",
    description=(
        "Devuelve identificadores de modelos del catálogo, sin datos internos del inventario. "
        "Conserva los identificadores de productos retirados para poder quitarlos de la lista."
    ),
)
def list_saved_products(
    identity: CustomerUser,
    session: DatabaseSession,
    parameters: Annotated[EmptyParameters, Query()],
) -> SavedProductsRead:
    assert identity.user_id is not None
    return saved_product_ids(session, identity.user_id)


@router.put(
    "/{equipment_id}",
    response_model=SavedProductsRead,
    responses=ERROR_RESPONSES,
    summary="Guardar un producto activo una sola vez",
    description="Las unidades físicas del mismo modelo comparten un único producto guardado.",
)
def save_product(
    equipment_id: PositiveId,
    identity: CustomerUser,
    session: DatabaseSession,
    parameters: Annotated[EmptyParameters, Query()],
    data: Annotated[EmptyParameters | None, Body()] = None,
) -> SavedProductsRead:
    assert identity.user_id is not None
    with immediate_transaction(session):
        equipment = session.get(Equipment, equipment_id)
        if equipment is None or not equipment.active:
            raise EquipmentNotFound
        canonical = active_product_units(session, equipment)[0]
        key = product_key(canonical)
        if not any(
            product_key(item) == key for _saved, item in saved_rows(session, identity.user_id)
        ):
            session.add(SavedProduct(customer_user_id=identity.user_id, equipment_id=canonical.id))
            session.flush()
        result = saved_product_ids(session, identity.user_id)
    return result


@router.delete(
    "/{equipment_id}",
    response_model=SavedProductsRead,
    responses=ERROR_RESPONSES,
    summary="Quitar un producto guardado, incluso si se ha retirado del catálogo",
    description="Operación idempotente; también admite identificadores de unidades del modelo.",
)
def remove_saved_product(
    equipment_id: PositiveId,
    identity: CustomerUser,
    session: DatabaseSession,
    parameters: Annotated[EmptyParameters, Query()],
    data: Annotated[EmptyParameters | None, Body()] = None,
) -> SavedProductsRead:
    assert identity.user_id is not None
    with immediate_transaction(session):
        equipment = session.get(Equipment, equipment_id)
        if equipment is not None:
            key = product_key(equipment)
            for saved, item in saved_rows(session, identity.user_id):
                if product_key(item) == key:
                    session.delete(saved)
            session.flush()
        result = saved_product_ids(session, identity.user_id)
    return result
