from pydantic import BaseModel, Field, field_validator


class ConfigModel(BaseModel):
    n_policies: int= Field (default=1000, description="Number of policies to simulate")
    projection_years: int= Field (default=10, gt=0, description="Number of years to project")
    random_seed: int=42
    
    target_avg_sum_assured : float= Field (default=50000, gt=0, 
                                           description="Target average sum assured for the policies")
    min_issue_age: int = Field (default=18, ge=0, description="Minimum issue age for the policies")
    max_issue_age: int = Field (default=55, ge=0, description="Maximum issue age for the policies")

    discount_rate: float = Field (default=0.05, gt=0, description="Discount rate for the policies")
    tax_rate: float = Field (default=0.20, ge=0, le=1, description="Tax rate for the policies")
    premium_margin: float = Field (default=1.2, gt=0, description="Premium margin for the policies")

    inflation_rate: float = Field (default=0.05, gt=0, description="Inflation rate for the policies")
    unit_cost: float = Field (default=1000.0, gt=0, description="Unit cost for the policies")   
    
    base_mort_rate: float = Field (default=0.001, gt=0, description="Base mortality rate for the policies")
    mortality_age_factor: float = Field (default=0.0001, gt=0, description="Mortality age factor for the policies")
    mortality_shock: float = Field (default=0.0005, gt=0, description="Mortality shock for the policies")

    lapse_decay: float = Field (default=0.15, gt=0, description="Lapse decay for the policies")
    lapse_base_rate: float = Field (default=0.10, gt=0, description="Lapse base rate for the policies")

    coc_ratio: float = Field (default=0.05, gt=0, description="Cost of capital ratio for the policies")
    s2_margin: float = Field (default=0.25, gt=0, description="S2 margin for the policies")
    op_risk_ratio: float = Field (default=0.02, gt=0, description="Operational risk ratio for the policies")

    reinsurance_cost: float = Field (default=0.4, gt=0, description="Reinsurance cost for the policies")
    counterparty_pd: float = Field (default=0.005, ge=0, le=1, description="Counterparty probability of default")
    counterparty_lgd: float = Field (default=0.6, ge=0, le=1, description="Counterparty loss given default")

    mortality_table_path: str = Field(
        default="data/mortality_table.csv",
        description="Path to the mortality table CSV file",
    )

    use_mortality_table: bool = Field(
        default=True,
        description="Flag to indicate whether mortality should be read from table",
    )

    run_scenarios: bool = Field(
        default=True,
        description="Flag to indicate whether scenario analysis should be executed",
    )


    confidence_level: float = Field (default=0.95, ge=0.5, le=1, description="Confidence level for the risk adjustment")
    n_risk_scenarios: int = Field (default=1000, gt=0, description="Number of risk scenarios to simulate for risk adjustment")
    acquisition_cost: float = Field (default=500.0, gt=0, description="Acquisition cost per policy")
    admin_cost_per_policy: float = Field (default=100.0, gt=0, description="Administrative cost per policy")
    collection_cost_rate: float = Field (default=0.02, gt=0, description="Collection cost as a percentage of premium")
    maintenance_cost_per_policy: float = Field (default=50.0, gt=0, description="Maintenance cost per policy")
    reinsurance_cost_rate: float = Field (default=0.4, gt=0, description="Reinsurance cost as a percentage of premium")
    surrender_charge_rate: float = Field (default=0.1, gt=0, description="Surrender charge as a percentage of sum assured")
    profit_margin: float = Field (default=0.2, gt=0, description="Profit margin as a percentage of premium")
    contingency_loading: float = Field (default=0.05, gt=0, description="Contingency loading as a percentage of premium")



    excel_output: bool = Field (default=True, description="Flag to indicate if Excel output is required")
    output_path: str = Field (default="output/ifrs17_results.xlsx", description="Path for the Excel output file")
    
    
    @field_validator('max_issue_age') 
    @classmethod
    def validate_age_range(cls, max_issue_age, info):
        min_age = info.data.get('min_issue_age')
        if min_age is not None and max_issue_age < min_age:
            raise ValueError("max_issue_age must be greater than or equal to min_issue_age")
        return max_issue_age


# Backward-compatible alias for earlier imports.
model_config = ConfigModel

# Backward-compatible alias for the user's preferred naming.
ModelConfig = ConfigModel