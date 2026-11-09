"""
DocuSense AI: Relational ORM Models for Auth & Multi-Tenancy
Feature Slug: auth-tenancy
Stage: 03-builds
Source Spec: database_production/workflows/02-specs/auth-tenancy-db-spec.md
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Base declarative class for all DocuSense SQLAlchemy models."""
    pass


class Company(Base):
    """
    Tenant Organization model.
    Represents commercial entities (importers, distributors, logistics providers)
    operating isolated document processing data silos.
    """
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
        comment="Unique tenant organization identifier",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Registered legal business name",
    )
    business_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Primary industry sector (importer, trading, logistics, retail)",
    )
    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        default="BD",
        server_default="BD",
        comment="ISO 3166-1 alpha-2 registered country code",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Company record creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        comment="Timestamp of last company record modification",
    )

    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    api_keys: Mapped[List["ApiKey"]] = relationship(
        "ApiKey",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "business_type IN ('importer', 'trading', 'logistics', 'retail')",
            name="chk_companies_business_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}', type='{self.business_type}')>"


class User(Base):
    """
    User Account model.
    Represents operators, reviewers, and tenant administrators accessing the system.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
        comment="Unique user account identifier",
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key referencing parent tenant company",
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Unique user login email address",
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Argon2id/Bcrypt salted password hash string",
    )
    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display and legal name of the user",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="operator",
        server_default="operator",
        comment="RBAC authorization role (admin, operator, viewer)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Account registration timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        comment="Last profile modification timestamp",
    )

    # Relationships
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="users",
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'operator', 'viewer')",
            name="chk_users_role",
        ),
        Index("idx_users_company_id", "company_id"),
        Index("uq_users_email", func.lower(email), unique=True),
        Index("idx_users_company_role", "company_id", "role"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


class ApiKey(Base):
    """
    Programmatic API Key model.
    Stores hashed credentials for external ERP/B2B automated document ingestion.
    """
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
        comment="Unique API key record identifier",
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key referencing parent tenant company",
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of the generated plaintext API secret",
    )
    key_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Descriptive label (e.g. 'SAP Production Connector')",
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional timestamp after which the key is revoked/expired",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Key issuance timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        server_default=func.now(),
        comment="Timestamp of last API key metadata update",
    )

    # Relationships
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="api_keys",
    )

    __table_args__ = (
        Index("idx_api_keys_company_id", "company_id"),
        Index("uq_api_keys_key_hash", "key_hash", unique=True),
    )

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, name='{self.key_name}', company_id={self.company_id})>"
