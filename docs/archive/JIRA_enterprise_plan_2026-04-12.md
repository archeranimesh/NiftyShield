# NiftyShield Architecture Backlog

> **Epic:** Modernize NiftyShield for Enterprise Scale (PostgreSQL Migration, Clean Architecture, Contextual Logging)  
> **Guidelines:** Follow strict Agile user stories. Smallest units of work, strictly ordered to heavily prevent breaking changes.

---

## Phase 1: Observability & Core Foundations

### [US-1]: Integrate `loguru` for Contextual Structured Logging
**As a** system maintainer,  
**I want** to integrate `loguru` to replace standard Python `logging` and arbitrary `print()` statements  
**So that** I can easily trace execution context (like `snapshot_date`) across heavy asynchronous I/O processes.

**Definition of Done (DoD):**
- `loguru` is added to `requirements.txt`.
- A centralized logging setup is declared (e.g., in `src/utils/logger.py`) handling console formatting.
- `logger.bind(snapshot_date=snap_date)` is utilized within the daily snapshot script.
- Existing `print()` statements in `daily_snapshot.py` and `tracker.py` are successfully replaced with `logger.info/debug/warning`.
- Tests pass.

---

## Phase 2: Data Abstraction (The Postgres Armor)

### [US-2]: Implement SQLAlchemy 2.0 Core Data Tables
**As a** backend developer,  
**I want** to map my SQLite raw tables to SQLAlchemy 2.0 Core `Table` configurations  
**So that** the database schema definitions become dialect-agnostic, preparing us for the PostgreSQL migration.

**Definition of Done (DoD):**
- SQLAlchemy is added to `requirements.txt`.
- `src/db/tables.py` is created with SQLAlchemy `MetaData` mappings reflecting the exact SQLite tables currently used.
- This story introduces *no breaking changes*; the existing `db.py` raw queries remain active.

### [US-3]: Define Pure Repository Interfaces (Protocols)
**As a** system architect,  
**I want** to define pure Python Protocols for `IPortfolioRepository` and `IMFRepository`  
**So that** our core domain tracker logic is fully decoupled from the actual implementation of SQLite or Postgres.

**Definition of Done (DoD):**
- `src/portfolio/interfaces.py` and `src/mf/interfaces.py` are defined containing methods like `get_all_strategies()`, `record_snapshots()`.
- The domain relies rigidly on `src/models/` objects with no SQL mappings.

### [US-4]: Implement the Unit of Work (UoW) Context Manager
**As a** domain engineer,  
**I want** to implement a Unit of Work context manager  
**So that** I can cleanly manage database transactions, rollbacks, and atomic writes without scattering `commit()` calls across tracker files.

**Definition of Done (DoD):**
- Create `src/db/uow.py`.
- Includes `class SqlAlchemyUnitOfWork` utilizing the newly defined Repository interfaces.
- The UoW yields access to cleanly scoped Repositories inside a `with` block context manager.

### [US-5]: Refactor `PortfolioTracker` to utilize Repositories and UoW
**As a** backend developer,  
**I want** to swap the legacy `PortfolioStore` out with the new UoW and SQLAlchemy Repositories  
**So that** the application safely abandons the tech debt of manual SQLite string bindings.

**Definition of Done (DoD):**
- Update `PortfolioTracker` signature to accept an `AbstractUnitOfWork` instead of the raw store.
- Eradicate manual `sqlite3` execution maps and `@staticmethod _row_to_X` tech debt.
- All 599+ tests pass using an `InMemory` or isolated SQLite SQLAlchemy repository adapter.

---

## Phase 3: Service Layer & Facades

### [US-6]: Implement the `MarketDataFacade`
**As a** domain engineer,  
**I want** to encapsulate Upstox, Dhan, and Nuvama data ingestion inside a unified `MarketDataFacade`  
**So that** the orchestration layer no longer has to manually enrich or merge datasets across distinct brokers.

**Definition of Done (DoD):**
- `src/market_data/facade.py` is established.
- `MarketDataFacade.get_enriched_portfolio_snapshot()` internally parses Nuvama, queries Dhan, gets Upstox keys, processes batch LTPs, and outputs domain objects safely handling any API 500s internally.

### [US-7]: Implement Application Use Cases (Service Layer)
**As a** system architect,  
**I want** to extract the orchestration logic of the daily snapshot processing into a `RecordDailySnapshotUseCase`  
**So that** all core business flows are isolated from the CLI presentation script.

**Definition of Done (DoD):**
- File `src/application/use_cases/snapshot_service.py` is active.
- It is instantiated with `UnitOfWork` and `MarketDataFacade`.
- It executes the entire sequence of `_async_main` successfully.

### [US-8]: Neutralize the `daily_snapshot.py` Script
**As a** terminal user,  
**I want** the `scripts/daily_snapshot.py` to act as a dumb CLI  
**So that** the single responsibility principle is respected and the script solely parses inputs and outputs exit codes.

**Definition of Done (DoD):**
- `daily_snapshot.py` logic is truncated to simply reading `sys.argv`, instantiating the injected `UseCase`, checking the result, and calling `sys.exit()`.
- No deep try/excepts or loop parsing exists in the script folder.

---

## Phase 4: Structural Design Patterns

### [US-9]: Implement Composite Pattern for P&L Computations
**As a** domain engineer,  
**I want** to define an `IPnLAsset` interface across Leg, Strategy, and Portfolio models  
**So that** cascading P&L summations can be executed simply by calling `obj.compute_pnl()`.

**Definition of Done (DoD):**
- Protocol implemented across structural boundaries.
- Deprecate explicit external loops performing manual addition math inside the tracker objects.

### [US-10]: Implement Strategy Pattern for Option Greeks Pricing
**As a** quantitative engineer,  
**I want** to isolate Greek extraction via an `IOptionPricer` strategy  
**So that** we can plugin Upstox Live APIs natively, but seamlessly swap to a local Black-Scholes module for offline backtesting.

**Definition of Done (DoD):**
- The `_fetch_greeks()` bypass is eliminated.
- Implemented via a Strategy interface so the tracker engine does not care how Greeks are evaluated.
