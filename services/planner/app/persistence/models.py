"""SQLAlchemy models for the planner service."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PlanStatus(enum.Enum):
    draft = "Draft"
    winning = "Winning"
    fallback = "Fallback"


class NodeDomain(enum.Enum):
    db = "DB"
    be = "BE"
    fe = "FE"
    test = "Test"
    package = "Package"
    data_pipeline = "Data-Pipeline"


class Plan(Base):
    __tablename__ = "plan"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    contract_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    wall_time_ms: Mapped[int | None] = mapped_column(Integer)
    token_cost: Mapped[int | None] = mapped_column(Integer)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    report_ref: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)

    nodes: Mapped[list["PlanNode"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    edges: Mapped[list["PlanEdge"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    candidates: Mapped[list["PlanCandidate"]] = relationship(back_populates="plan", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("project_id", "run_id", name="uq_plan_project_run"),)


class PlanNode(Base):
    __tablename__ = "plan_node"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan.id"), nullable=False)
    type: Mapped[NodeDomain] = mapped_column(Enum(NodeDomain), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    instructions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    artifacts_in: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    artifacts_out: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    token_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    order_hint: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    plan: Mapped[Plan] = relationship(back_populates="nodes")
    outgoing: Mapped[list["PlanEdge"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        foreign_keys="PlanEdge.from_node",
    )
    incoming: Mapped[list["PlanEdge"]] = relationship(
        back_populates="target",
        cascade="all, delete-orphan",
        foreign_keys="PlanEdge.to_node",
    )
    complexity: Mapped[ComplexityFeatures | None] = relationship(back_populates="node", uselist=False, cascade="all, delete-orphan")
    context_cards: Mapped[list["ContextCard"]] = relationship(back_populates="node", cascade="all, delete-orphan")


class PlanEdge(Base):
    __tablename__ = "plan_edge"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan.id"), nullable=False)
    from_node: Mapped[str] = mapped_column(ForeignKey("plan_node.id"), nullable=False)
    to_node: Mapped[str] = mapped_column(ForeignKey("plan_node.id"), nullable=False)
    artifact_type: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)

    plan: Mapped[Plan] = relationship(back_populates="edges")
    source: Mapped[PlanNode] = relationship(foreign_keys=[from_node], back_populates="outgoing")
    target: Mapped[PlanNode] = relationship(foreign_keys=[to_node], back_populates="incoming")


class PlanCandidate(Base):
    __tablename__ = "plan_candidate"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id: Mapped[str] = mapped_column(ForeignKey("plan.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    trace: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    plan: Mapped[Plan] = relationship(back_populates="candidates")

    __table_args__ = (UniqueConstraint("plan_id", "rank", name="uq_candidate_plan_rank"),)


class ContextCard(Base):
    __tablename__ = "context_card"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    node_id: Mapped[str] = mapped_column(ForeignKey("plan_node.id"), nullable=False)
    contract_slice_ref: Mapped[str] = mapped_column(String, nullable=False)
    interfaces: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    schema_hashes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    node: Mapped[PlanNode] = relationship(back_populates="context_cards")


class ComplexityFeatures(Base):
    __tablename__ = "complexity_features"

    node_id: Mapped[str] = mapped_column(ForeignKey("plan_node.id"), primary_key=True)
    d: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    s: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    n: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    a: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    r: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    ccs: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    recommended_subtasks: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)

    node: Mapped[PlanNode] = relationship(back_populates="complexity")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    principal: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    old_val: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_val: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    correlation_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


__all__ = [
    "Base",
    "Plan",
    "PlanNode",
    "PlanEdge",
    "PlanCandidate",
    "ContextCard",
    "ComplexityFeatures",
    "AuditLog",
    "PlanStatus",
    "NodeDomain",
]
