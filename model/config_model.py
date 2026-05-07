from pydantic import BaseModel, Field, field_validator

class model_config(BaseModel):
    n_policies: int= Field (default=1000, description="Number of policies to simulate")
    projection_years: int= Field (default=10, gt=0, description="Number of years to project")
    random_seeds: int=42
    
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

    excel_output: bool = Field (default=True, description="Flag to indicate if Excel output is required")
    output_path: str = Field (default="output/ifrs17_results.xlsx", description="Path for the Excel output file")
    
    @field_validator('max_issue_age') 
    @classmethod
    def validate_age_range(cls, max_issue_age, info):
        min_age = info.data.get('min_issue_age')
        if min_age is not None and max_issue_age < min_age:
            raise ValueError("max_issue_age must be greater than or equal to min_issue_age")
        return max_issue_age