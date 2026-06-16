import datetime
from sqlalchemy import Column, Integer, Numeric, Float, Boolean, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class FinancialAuditTrail(Base):
    __tablename__ = 'financial_audit_trail'
    
    audit_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    asset_id = Column(Integer, nullable=False)
    simulation_timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    simulated_year = Column(Integer, nullable=False)
    capacity_multiplier = Column(Float, nullable=False)
    production_mwh = Column(Numeric(12, 2), nullable=False)
    revenue_eur = Column(Numeric(12, 2), nullable=False)
    opex_eur = Column(Numeric(12, 2), nullable=False)
    debt_service_eur = Column(Numeric(12, 2), nullable=False)
    net_profit_eur = Column(Numeric(12, 2), nullable=False)
    dscr = Column(Float, nullable=False)
    covenant_breached = Column(Boolean, nullable=False)
    simulation_parameters = Column(JSON, nullable=False)

def write_audit_trail(engine, audit_records):
    """
    Performant batch-inserts financial metrics using SQLAlchemy Core execution.
    """
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Use bulk_insert_mappings for maximal performance in timeseries pipelines
        session.bulk_insert_mappings(FinancialAuditTrail, audit_records)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
