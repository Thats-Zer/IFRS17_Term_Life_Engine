from pydantic import BaseModel, Field, field_validator, model_validator
#integer veri tipi sadece tam sayıları temsil ederken, float veri tipi ondalık sayıları temsil eder.
#boolean veri tipi True veya False değerlerini temsil ederken, string veri tipi metin verilerini temsil eder.
#ge=0 ifadesi, ilgili alanın değerinin 0 veya daha büyük olması gerektiğini belirtir.
# Bu, negatif değerlerin kabul edilmemesi gerektiği durumlarda kullanılır.

#gt=0 ifadesi, ilgili alanın değerinin 0'den büyük olması gerektiğini belirtir.
# Bu, sıfırın kabul edilmediği durumlarda kullanılır.

class ConfigModel(BaseModel):
    n_policies: int= Field (default=1000, description="Number of policies to simulate")
    #simüle edilecek poliçe sayısını belirtir. Bu, modelin ne kadar büyük bir veri seti üzerinde çalışacağını belirler.
    
    projection_years: int= Field (default=10, gt=0, description="Number of years to project")
    #projeksiyon yılını belirtir. Bu, modelin ne kadar uzun bir süre için projeksiyon yapacağını belirler.

    coverage_years: int = Field(
        default=10,
        gt=0,
        description="Policy coverage/term length in years (must be <= projection_years)",
    )
    
    random_seed: int=42
    #rastgele sayı üreteci için kullanılan başlangıç değerini belirtir. Bu, modelin her çalıştırıldığında aynı sonuçları üretmesini sağlar.
    
    target_avg_sum_assured : float= Field (default=50000, gt=0, 
                                           description="Target average sum assured for the policies")
    #policelerin ortalama teminat tutarını belirtir. Bu, modelin oluşturduğu poliçelerin ne kadar teminat sağladığını belirler.

    min_issue_age: int = Field (default=18, ge=0, description="Minimum issue age for the policies")
    #policelerin minimum başlangıç yaşını belirtir. Bu, modelin oluşturduğu poliçelerin hangi yaş aralığında olduğunu belirler.
    
    max_issue_age: int = Field (default=55, ge=0, description="Maximum issue age for the policies")
    #policelerin maksimum başlangıç yaşını belirtir. Bu, modelin oluşturduğu poliçelerin hangi yaş aralığında olduğunu belirler.

    discount_rate: float = Field (default=0.05, ge=0, description="Discount rate for the policies")
    #iskonto oranını belirtir. Bu, modelin gelecekteki nakit akışlarını bugünkü değerlerine dönüştürmesinde kullanılan orandır.

    tax_rate: float = Field (default=0.20, ge=0, le=1, description="Tax rate for the policies")
    #policeler için geçerli olan vergi oranını belirtir. Bu, modelin vergi etkilerini hesaplamasında kullanılan orandır.

    premium_margin: float = Field (default=1.2, gt=0, description="Premium margin for the policies")
    #prim marjını belirtir. Bu, modelin hesapladığı primlerin üzerine eklenen marjı ifade eder.

    inflation_rate: float = Field (default=0.05, ge=0, description="Inflation rate for the policies")
    #enflasyon oranını belirtir. Bu, modelin gelecekteki nakit akışlarını enflasyona göre ayarlamasında kullanılan orandır.

    unit_cost: float = Field (default=1000.0, gt=0, description="Unit cost for the policies")   
    #policelerin birim maliyetini belirtir. Bu, modelin her bir poliçe için hesapladığı maliyeti ifade eder.

    base_mort_rate: float = Field (default=0.001, gt=0, description="Base mortality rate for the policies")
    #policeler için geçerli olan temel ölüm oranını belirtir. Bu, modelin ölüm riskini hesaplamasında kullanılan orandır.

    mortality_age_factor: float = Field (default=0.0001, gt=0, description="Mortality age factor for the policies")
    #policelerin yaş faktörünü belirtir. Bu, modelin ölüm riskini yaşa göre ayarlamasında kullanılan orandır.

    mortality_shock: float = Field (default=0.0005, ge=0, description="Mortality shock for the policies")
    #policeler için geçerli olan ölüm şokunu belirtir. Bu, modelin beklenmedik ölüm risklerini hesaba katmasında kullanılan orandır.

    lapse_decay: float = Field (default=0.15, ge=0, description="Lapse decay for the policies")
    #policelerin lapse decay oranını belirtir. Bu, modelin lapse riskini zamanla azalan bir şekilde hesaplamasında kullanılan orandır.

    lapse_base_rate: float = Field (default=0.10, ge=0, description="Lapse base rate for the policies")
    #policeler için geçerli olan temel lapse oranını belirtir. Bu, modelin lapse riskini hesaplamasında kullanılan orandır.

    coc_ratio: float = Field (default=0.05, ge=0, description="Cost of capital ratio for the policies")
    #policeler için geçerli olan sermaye maliyeti oranını belirtir. Bu, modelin sermaye maliyetini hesaplamasında kullanılan orandır.

    s2_margin: float = Field (default=0.25, gt=0, description="S2 margin for the policies")
    #policeler için geçerli olan S2 marjını belirtir. Bu, modelin IFRS 17'ye göre risk marjını hesaplamasında kullanılan orandır.

    op_risk_ratio: float = Field (default=0.02, gt=0, description="Operational risk ratio for the policies")
    #policeler için geçerli olan operasyonel risk oranını belirtir. Bu, modelin operasyonel risk maliyetini hesaplamasında kullanılan orandır.

    reinsurance_cost: float = Field (default=0.4, gt=0, description="Reinsurance cost for the policies")
    #policeler için geçerli olan reasekürans maliyetini belirtir. Bu, modelin reasekürans masraflarını hesaplamasında kullanılan orandır.

    counterparty_pd: float = Field (default=0.005, ge=0, le=1, description="Counterparty probability of default")
    #karşı tarafın temerrüt olasılığını belirtir.
    # Bu, modelin karşı taraf riskini hesaplamasında kullanılan orandır.

    counterparty_lgd: float = Field (default=0.6, ge=0, le=1, description="Counterparty loss given default")
    #karşı tarafın temerrüt durumunda oluşacak kayıp oranını belirtir.

    mortality_table_path: str = Field(
        default="data/mortality_table.csv",
        description="Path to the mortality table CSV file",
        # Bu, modelin ölüm oranlarını hesaplamak için kullanacağı mortalite tablosunun dosya yolunu belirtir.
    )


    use_mortality_table: bool = Field(
        default=True,
        description="Flag to indicate whether mortality should be read from table",
        # Bu, modelin ölüm oranlarını hesaplamak için mortalite tablosunu kullanıp kullanmayacağını belirten bir bayraktır.
    )


    run_scenarios: bool = Field(
        default=True,
        description="Flag to indicate whether scenario analysis should be executed",
        # Bu, modelin senaryo analizinin yürütülmesi gerekip gerekmediğini belirten bir bayraktır.
    )


    # ==================================================
    # SCENARIO / SHOCK PARAMETERS (optional)
    # ==================================================

    discount_rate_shift: float = Field(
        default=0.0,
        description="Scenario shock: additive shift to discount_rate (e.g. -0.01 for -100bps)",
    )

    mortality_shock_multiplier: float = Field(
        default=1.0,
        gt=0,
        description="Scenario shock: multiplier applied to mortality qx (e.g. 1.10 for +10%)",
    )

    lapse_initial_rate_multiplier: float = Field(
        default=1.0,
        gt=0,
        description="Scenario shock: multiplier applied to lapse_base_rate",
    )

    unit_expense_multiplier: float = Field(
        default=1.0,
        gt=0,
        description="Scenario shock: multiplier applied to expense assumptions",
    )

    scenario_max_workers: int = Field(
        default=1,
        gt=0,
        description="Max parallel workers for scenario runs",
    )

    reporting_year: int = Field(
        default=1,
        gt=0,
        description="Reporting year used for single-period CSM rollforward release",
    )

    issue_year: int = Field(
        default=2026,
        gt=1900,
        description="Default synthetic issue year used for annual cohort grouping",
    )

    portfolio_id: str = Field(
        default="TERM_LIFE",
        description="Default IFRS 17 portfolio identifier",
    )

    methodology_version: str = Field(
        default="ifrs17-term-life-educational-v1",
        description="Methodology version recorded in audit outputs",
    )

    approval_status: str = Field(
        default="development",
        description="Governance status recorded in audit outputs",
    )

    locked_in_discount_rate: float | None = Field(
        default=None,
        ge=0,
        description="Optional locked-in rate for disclosure and governance tracking",
    )

    ra_mortality_sigma: float = Field(
        default=0.10,
        ge=0,
        description="Lognormal volatility for mortality risk adjustment scenarios",
    )

    ra_lapse_sigma: float = Field(
        default=0.15,
        ge=0,
        description="Lognormal volatility for lapse risk adjustment scenarios",
    )

    ra_expense_sigma: float = Field(
        default=0.10,
        ge=0,
        description="Lognormal volatility for expense risk adjustment scenarios",
    )


    # ==================================================
    # NUMERICS (optional)
    # ==================================================

    use_float64: bool = Field(
        default=False,
        description="If True, use float64 for selected PV/aggregation calculations to reduce rounding error",
    )


    confidence_level: float = Field (default=0.95, ge=0.5, le=1, description="Confidence level for the risk adjustment")
    # Bu, modelin risk ayarlaması için kullanacağı güven düzeyini belirtir. Genellikle 0.95 veya 0.99 gibi değerler kullanılır.

    n_risk_scenarios: int = Field (default=1000, gt=0, description="Number of risk scenarios to simulate for risk adjustment")
    # Bu, modelin risk ayarlaması için simüle edeceği risk senaryolarının sayısını belirtir. Daha fazla senaryo, daha doğru bir risk ayarlaması sağlar ancak hesaplama süresini artırır.

    acquisition_cost: float = Field (default=500.0, gt=0, description="Acquisition cost per policy")
    #policelerin edinim maliyetini belirtir. Bu, modelin her bir poliçe için hesapladığı edinim maliyetini ifade eder.

    admin_cost_per_policy: float = Field (default=100.0, gt=0, description="Administrative cost per policy")
    #policelerin yönetimsel maliyetini belirtir. Bu, modelin her bir poliçe için hesapladığı yönetimsel maliyetini ifade eder.

    collection_cost_rate: float = Field (default=0.02, gt=0, description="Collection cost as a percentage of premium")
    #policelerin tahsilat maliyetini belirtir. Bu, modelin primlerin yüzde kaçını tahsilat maliyeti olarak hesaplayacağını ifade eder.

    maintenance_cost_per_policy: float = Field (default=50.0, gt=0, description="Maintenance cost per policy")
    #policelerin bakımı maliyetini belirtir. Bu, modelin her bir poliçe için hesapladığı bakım maliyetini ifade eder.

    reinsurance_cost_rate: float = Field (default=0.4, gt=0, description="Reinsurance cost as a percentage of premium")
    #policelerin reasürans maliyetini belirtir. Bu, modelin primlerin yüzde kaçını reasekürans maliyeti olarak hesaplayacağını ifade eder.

    surrender_charge_rate: float = Field (default=0.1, gt=0, description="Surrender charge as a percentage of sum assured")
    #policelerin iptal ücreti oranını belirtir. Bu, modelin teminat tutarının yüzde kaçını iptal ücreti olarak hesaplayacağını ifade eder.

    profit_margin: float = Field (default=0.2, gt=0, description="Profit margin as a percentage of premium")
    #policelerin kar marjını belirtir. Bu, modelin primlerin yüzde kaçını kar marjı olarak hesaplayacağını ifade eder.

    contingency_loading: float = Field (default=0.05, gt=0, description="Contingency loading as a percentage of premium")
    #policelerin beklenmedik durum yüklemesini belirtir. Bu, modelin primlerin yüzde kaçını beklenmedik durum yüklemesi olarak hesaplayacağını ifade eder.

    excel_output: bool = Field (default=True, description="Flag to indicate if Excel output is required")
    # Bu, modelin Excel çıktısı gerekip gerekmediğini belirten bir bayraktır.

    output_path: str = Field (default="outputs/ifrs17_term_life_projection.xlsx", description="Path for the Excel output file")
    # Bu, modelin Excel çıktısı için dosya yolunu belirtir.


    @field_validator("max_issue_age")
    def validate_age_range(max_issue_age, info):
        min_age = info.data.get("min_issue_age")
        if min_age is not None and max_issue_age < min_age:
            raise ValueError("max_issue_age must be >= min_issue_age")
        return max_issue_age


    @field_validator("coverage_years")
    def validate_coverage_years(coverage_years, info):
        projection_years = info.data.get("projection_years")
        if projection_years is not None and coverage_years > projection_years:
            raise ValueError("coverage_years must be <= projection_years")
        return coverage_years


    @model_validator(mode="after")
    def _backward_compat_reinsurance_rate(self):
        # Backward compatibility:
        # Some configs use `reinsurance_cost` while the engine consumes `reinsurance_cost_rate`.
        # If rate was not explicitly set, mirror it from cost.
        try:
            fields_set = self.model_fields_set
        except Exception:
            fields_set = set()

        if "reinsurance_cost_rate" not in fields_set and "reinsurance_cost" in fields_set:
            self.reinsurance_cost_rate = self.reinsurance_cost
        return self


model_config = ConfigModel
# Bu, modelin yapılandırma parametrelerini içeren bir sınıf tanımlar. Kullanıcı, bu sınıfı kullanarak modelin nasıl çalışacağını belirleyen çeşitli parametreleri ayarlayabilir.


ModelConfig = ConfigModel
# Bu, modelin yapılandırma parametrelerini içeren bir sınıf tanımlar.
