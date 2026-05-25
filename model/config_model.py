from pydantic import BaseModel, Field, field_validator, model_validator


class ConfigModel(BaseModel):
    n_policies: int = Field(default=1000, gt=0, description="Number of policies to simulate")
    projection_years: int = Field(default=10, gt=0, description="Number of years to project")
    coverage_years: int = Field(
        default=10,
        gt=0,
        description="Policy coverage/term length in years",
    )
    random_seed: int = Field(default=42, description="Random seed for reproducible synthetic data")

    target_avg_sum_assured: float = Field(default=50000, gt=0)
    sum_assured_sigma: float = Field(default=0.8, ge=0)
    min_issue_age: int = Field(default=18, ge=0)
    max_issue_age: int = Field(default=55, ge=0)

    discount_rate: float = Field(default=0.05, ge=0)
    tax_rate: float = Field(default=0.20, ge=0, le=1)
    premium_margin: float = Field(
        default=1.2,
        gt=0,
        description="Legacy gross/net premium multiplier; used only when profit_margin is not supplied",
    )

    inflation_rate: float = Field(default=0.05, ge=0)
    unit_cost: float = Field(
        default=1000.0, gt=0, description="Legacy field retained for old configs"
    )

    base_mort_rate: float = Field(default=0.001, gt=0)
    mortality_age_factor: float = Field(default=0.0001, gt=0)
    mortality_shock: float = Field(default=0.0005, ge=0)
    lapse_mortality_correlation: float = Field(default=0.1, ge=0, le=1)

    lapse_decay: float = Field(default=0.15, ge=0)
    lapse_base_rate: float = Field(default=0.10, ge=0)

    coc_ratio: float = Field(default=0.05, ge=0, le=1)
    s2_margin: float = Field(
        default=0.25, gt=0, description="Legacy field retained for old configs"
    )
    op_risk_ratio: float = Field(
        default=0.02, gt=0, description="Legacy field retained for old configs"
    )

    reinsurance_cost: float = Field(default=0.4, gt=0)
    counterparty_pd: float = Field(default=0.005, ge=0, le=1)
    counterparty_lgd: float = Field(default=0.6, ge=0, le=1)

    mortality_table_path: str = Field(default="data/mortality_table.csv")
    use_mortality_table: bool = Field(default=True)
    run_scenarios: bool = Field(default=True)

    sample_policy_path: str | None = Field(
        default=None,
        description="Optional path to a sample policy CSV input for data lineage demonstrations",
    )

    discount_rate_shift: float = Field(default=0.0)
    mortality_shock_multiplier: float = Field(default=1.0, gt=0)
    lapse_initial_rate_multiplier: float = Field(default=1.0, gt=0)
    unit_expense_multiplier: float = Field(default=1.0, gt=0)
    scenario_max_workers: int = Field(default=1, gt=0)

    reporting_year: int = Field(default=1, gt=0)
    issue_year: int = Field(default=2026, gt=1900)
    portfolio_id: str = Field(default="TERM_LIFE")
    methodology_version: str = Field(default="ifrs17-term-life-educational-v1")
    approval_status: str = Field(default="development")
    locked_in_discount_rate: float | None = Field(default=None, ge=0)

    ra_mortality_sigma: float = Field(default=0.10, ge=0)
    ra_lapse_sigma: float = Field(default=0.15, ge=0)
    ra_expense_sigma: float = Field(default=0.10, ge=0)

    use_float64: bool = Field(
        default=False,
        description="Use float64 for selected PV and aggregation calculations",
    )

    confidence_level: float = Field(default=0.95, ge=0.5, le=1)
    n_risk_scenarios: int = Field(default=1000, gt=0)

    acquisition_cost: float = Field(default=500.0, ge=0)
    admin_cost_per_policy: float = Field(default=100.0, ge=0)
    collection_cost_rate: float = Field(default=0.02, ge=0, le=1)
    maintenance_cost_per_policy: float = Field(default=50.0, ge=0)
    reinsurance_cost_rate: float = Field(default=0.4, ge=0)
    surrender_value_rate: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Term-life cash surrender value as a share of annual net premium",
    )
    surrender_charge_rate: float = Field(default=0.1, ge=0, le=1)
    profit_margin: float = Field(default=0.2, ge=0, le=1)
    contingency_loading: float = Field(default=0.05, ge=0, le=1)

    excel_output: bool = Field(default=True)
    output_path: str = Field(default="outputs/ifrs17_term_life_projection.xlsx")

    enable_bel_diagnostics: bool = Field(
        default=True,
        description="Enable structured BEL diagnostic summary and detailed logging. "
        "Set to False for large production-scale runs to reduce logging overhead.",
    )

    @field_validator("max_issue_age")
    def validate_age_range(cls, max_issue_age, info):
        min_age = info.data.get("min_issue_age")
        if min_age is not None and max_issue_age < min_age:
            raise ValueError("max_issue_age must be >= min_issue_age")
        return max_issue_age

    @field_validator("coverage_years")
    def validate_coverage_years(cls, coverage_years, info):
        projection_years = info.data.get("projection_years")
        if projection_years is not None and coverage_years > projection_years:
            raise ValueError("coverage_years must be <= projection_years")
        return coverage_years

    @model_validator(mode="after")
    def _backward_compat_reinsurance_rate(self):
        fields_set = getattr(self, "model_fields_set", set())
        if "profit_margin" not in fields_set and "premium_margin" in fields_set:
            self.profit_margin = max(float(self.premium_margin) - 1.0, 0.0)
        if "reinsurance_cost_rate" not in fields_set and "reinsurance_cost" in fields_set:
            self.reinsurance_cost_rate = self.reinsurance_cost
        return self


model_config = ConfigModel
ModelConfig = ConfigModel
