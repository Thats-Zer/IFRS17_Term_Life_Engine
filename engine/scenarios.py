from copy import deepcopy #bu, senaryo yapılandırmalarını temel yapılandırmadan türetmek için kullanılır.
#Böylece her senaryo, temel yapılandırmanın bir kopyası olarak başlar
# sadece ilgili parametreler değiştirilir.

from concurrent.futures import ThreadPoolExecutor, as_completed
#Bu, senaryoların paralel olarak çalıştırılmasını sağlar. Paralel olarak çalıştırma yaparak zaman tasarrufu elde ederiz.

from typing import Optional
#Bu, senaryo sonuçlarının sözlükler halinde döndürüleceğini belirtir, her bir senaryo bir sonuç listesi/ sözlüğü oluşturur.

import gc #Bu, senaryo çalıştırmaları sırasında bellek yönetimi ve optimizasyonu için kullanılır.

import pandas as pd #Bu, veri manipülasyonu ve analiz için kullanılır. Bizim veri çerçevesi oluşturmamızısağlar.

import logging

from model.config_model import ModelConfig 
#Bu, modelin yapılandırma parametrelerini içeren sınıfı içe aktarır.

from engine.curves import create_discount_curve
#Bu, senaryoların çalıştırılması sırasında kullanılacak iskonto eğrisini oluşturmak için kullanılan fonksiyonu içe aktarır.

from engine.projection import (
    
    create_master_data, 
    #Bu, senaryoların çalıştırılması sırasında kullanılacak veri setini içe aktarır.
    #    
    create_projection_table,
    #Bu, senaryoların çalıştırılması sırasında kullanılacak projeksiyon tablosunu oluşturmak için kullanılan fonksiyonu içe aktarır.
)

from engine.cashflows import calculate_cashflows
#Bu, senaryoların çalıştırılması sırasında kullanılacak nakit akışlarını hesaplamak için kullanılan fonksiyonu içe aktarır.

from engine.bel import calculate_bel
#Bu, senaryoların çalıştırılması sırasında kullanılacak Best Estimate Liability (BEL) hesaplamak için kullanılan fonksiyonu içe aktarır.

from engine.ra import calculate_risk_adjustment
from engine.csm import calculate_csm_rollforward
#Bu, senaryoların çalıştırılması sırasında kullanılacak Risk Adjustment (RA) hesaplamak için kullanılan fonksiyonu içe aktar


logger = logging.getLogger(__name__)


SCENARIOS = {
    "base": {}, #Bu, temel senaryoyu temsil eder.
    #Hiçbir parametre değiştirilmez, bu nedenle modelin varsayılan yapılandırması kullanılır.
   
    "mortality_up_10": {"mortality_shock_multiplier": 1.10},
    #Bu, ölüm şokunu yüzde 10 artıran bir senaryoyu temsil eder.
    
    "lapse_up_20": {"lapse_initial_rate_multiplier": 1.20},
    #Bu, başlangıç lapse oranını yüzde 20 artıran bir senaryoyu temsil eder.
    
    "expense_up_15": {"unit_expense_multiplier": 1.15},
    #Bu, birim giderleri yüzde 15 artıran bir senaryoyu temsil eder.
    
    "discount_down_100bps": {"discount_rate_shift": -0.01},
    #Bu, iskonto oranını 100 basis point azaltan bir senaryoyu temsil eder.
}


def apply_scenario(config: ModelConfig, scenario: dict) -> ModelConfig:
    #Bu fonksiyon, temel yapılandırmayı alır ve senaryo parametreleriyle güncelleyerek yeni bir yapılandırma oluşturur.
    
    if hasattr(config, "model_copy"):
        #Bu, Pydantic v2'deki model_copy yöntemini kullanarak yapılandırmayı günceller.
        return config.model_copy(update=scenario) 

    cfg = deepcopy(config)
    for k, v in scenario.items(): #scenario sözlüğündeki her parametre ve değeri için:
        #setattr fonksiyonunu kullanarak temel yapılandırma nesnesine bu parametreleri uygular.
        setattr(cfg, k, v)
    return cfg


def run_single_scenario(
    index: str, #Senaryo adını belirtir.
    #Bu, sonuçların hangi senaryoya ait olduğunu tanımlamak için kullanılır.
    scenario_cfg: dict, #Bu, senaryo parametrelerini içeren bir sözlüktür.
    #Bu, senaryo çalıştırılırken kullanılacak parametreleri içerir.
    base_config: ModelConfig, #Bu, temel yapılandırmayı içeren bir ModelConfig nesnesidir.
    #Bu, senaryo çalıştırılırken kullanılacak temel yapılandırmayı belirtir.
    mortality_table: pd.DataFrame 
    #Bu, senaryo çalıştırılırken kullanılacak ölüm tablosunu içeren bir DataFrame'dir.

) -> Optional[dict]: 
    #Bu fonksiyon, tek bir senaryoyu çalıştırır ve sonuçları bir sözlük olarak döndürür.
    try:
        config = apply_scenario(base_config, scenario_cfg)
        #Bu, temel yapılandırmayı senaryo parametreleriyle güncelleyerek yeni bir yapılandırma oluşturur.
        master_data = create_master_data(config)
        #Bu, senaryo çalıştırılırken kullanılacak ana veri setini oluşturur.
        projection = create_projection_table(master_data, config, mortality_table)
        #Bu, senaryo çalıştırılırken kullanılacak projeksiyon tablosunu oluşturur.

        # --- Ensure Year int
        if "Year" not in projection.columns:
            raise ValueError("projection içinde 'Year' yok")
        projection["Year"] = projection["Year"].astype(int) 
        #Bu, projeksiyon tablosundaki "Year" sütununun tam sayı formatında olduğundan emin olur.
        #Kontrol mekanizması ekleyerek, eğer "Year" sütunu yoksa veya uygun formatta değilse, hata mesajı verir ve senaryonun çalışmasını durdurur.


        discount_curve = create_discount_curve(config).copy()
        if "Year" not in discount_curve.columns:
            raise ValueError("discount_curve içinde 'Year' yok")
        #Kontrol mekanizması ekleyerek, eğer iskonto eğrisi tablosunda "Year" sütunu yoksa veya uygun formatta değilse, hata mesajı verir ve senaryonun çalışmasını durdurur.
        discount_curve["Year"] = discount_curve["Year"].astype(int) 
        #Bu, iskonto eğrisi tablosundaki "Year" sütununun tam sayı formatında olduğundan emin olur.

        if "discount_factor" not in discount_curve.columns:
            raise ValueError("discount_curve içinde 'discount_factor' yok")
        if "discount_factor_opening" not in discount_curve.columns:
            discount_curve["discount_factor_opening"] = discount_curve["discount_factor"]
            #Bu, iskonto eğrisi tablosunda "discount_factor_opening" sütunu yoksa, "discount_factor" sütununu kopyalayarak "discount_factor_opening" sütununu oluşturur.


        curve_subset = (
            discount_curve[["Year", "discount_factor", "discount_factor_opening"]]
            .drop_duplicates(subset=["Year"])
        )
        #Bu, iskonto eğrisi tablosundan "Year", "discount_factor" ve "discount_factor_opening" sütunlarını seçer, ve "Year" sütunundaki tekrar eden değerleri kaldırır.

        projection = projection.merge(curve_subset, on="Year", how="left", validate="m:1")
        #Bu, projeksiyon tablosunu iskonto eğrisi tablosuyla "Year" sütunu üzerinden birleştirir.


        if "coverage_years" not in projection.columns:
            projection["coverage_years"] = int(getattr(config, "coverage_years", getattr(config, "projection_years", 1)) or 1)
        #Bu, projeksiyon tablosunda "coverage_years" sütunu yoksa, "Year" sütununu kopyalayarak "coverage_years" sütununu oluşturur.

        projection = calculate_cashflows(projection, config)
        #Bu, projeksiyon tablosuna nakit akışlarını hesaplayarak ekler.


        bel_result = calculate_bel(projection, config)
        #Bu, projeksiyon tablosunu kullanarak Best Estimate Liability (BEL) hesaplar sonuçları bel_result DataFrame'ine atar.

        ra_result = calculate_risk_adjustment(projection, config)
        csm_result = calculate_csm_rollforward(
            bel_result,
            ra_result,
            projection,
            config,
        )
        #Bu, projeksiyon tablosunu kullanarak Risk Adjustment (RA) hesaplar sonuçları ra_result DataFrame'ine atar.

       #Karşılaştırma döngüsü ile BEL sütununu kontrol ediyoruz. 
        if "bel_per_policy" in bel_result.columns:
            total_bel = float(bel_result["bel_per_policy"].sum())
        elif "BEL" in bel_result.columns:
            total_bel = float(bel_result["BEL"].sum())
        else:
            total_bel = float("nan")


        #Karşılaştırma döngüsü ile RA Sütununu kontrol ediyoruz.
        if "ra_per_policy" in ra_result.columns:
            total_ra = float(ra_result["ra_per_policy"].sum())
        elif "RA" in ra_result.columns:
            total_ra = float(ra_result["RA"].sum())
        else:
            total_ra = float("nan")

        total_csm_opening = float(csm_result["csm_opening"].sum())
        total_csm_closing = float(csm_result["csm_closing"].sum())
        onerous_count = int(csm_result["is_onerous"].sum())
        onerous_loss = float(csm_result["onerous_loss"].sum())

        #Sonuç olarak Senaryo yanıtlarını çevirir.
        return {
            "scenario": index, #Senaryo adını belirtir.
            # Bu, sonuçların hangi senaryoya ait olduğunu tanımlamak için kullanılır.
            "n_policies": int(getattr(config, "n_policies", len(master_data))),
            # Bu, senaryoda işlenecek poliçe sayısını belirtir.
            # Eğer yapılandırmada "n_policies" parametresi varsa onu kullanır, yoksa master_data'daki kayıt sayısını kullanır.
            "Total_BEL": total_bel,
            # Bu, senaryoda hesaplanan toplam Best Estimate Liability (BEL) değerini belirtir.
            "Total_RA": total_ra,
            "Total_CSM_Opening": total_csm_opening,
            "Total_CSM_Closing": total_csm_closing,
            "Onerous_Count": onerous_count,
            "Onerous_Loss": onerous_loss,
            # Bu, senaryoda hesaplanan toplam Risk Adjustment (RA) değerini belirtir.
        }

    except Exception as e:
        logger.warning(f"Error processing scenario {index}: {e}", exc_info=True)
        return None
    #Burada, senaryo çalıştırılırken herhangi bir hata oluşursa, hata mesajı yazdırılır ve None döndürülür.
    #None döndürülmesi, bu senaryonun sonuçlarının geçersiz olduğunu ve sonraki işlemlerde dikkate alınmaması gerektiğini belirtir.

    finally:
        gc.collect()
        #Bu, senaryo çalıştırmaları sırasında bellek kullanımını optimize etmek için garbage collection'ı manuel olarak tetikler.
        #Özellikle çok sayıda senaryo çalıştırırken, bellek kullanımını kontrol altında tutmak için önemlidir.


def run_scenarios(
    base_config: ModelConfig,
    scenarios: dict,
    mortality_table: pd.DataFrame
) -> pd.DataFrame:
    #Bu fonksiyon, verilen senaryoları paralel olarak çalıştırır ve sonuçları bir DataFrame olarak döndürür.

    max_workers = int(getattr(base_config, "scenario_max_workers", 1) or 1)
    #Bu, senaryoların paralel olarak çalıştırılacağı maksimum iş parçacığı sayısını belirler, "scenario_max_workers" parametresi varsa onu kullanır.
    
    max_workers = max(1, max_workers) #En az 1 iş parçacığı kullanılmasını sağlar.
    #Bu, maksimum iş parçacığı sayısının en az 1 olmasını garanti eder.

    results: list[dict] = [] #Bu, her senaryonun sonuçlarını içerecek bir liste oluşturur.

    # Senaryoları paralel olarak çalıştırmak için ThreadPoolExecutor kullanılır.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_single_scenario, name, cfg, base_config, mortality_table): name
            for name, cfg in scenarios.items()
        }
        for fut in as_completed(futures):
            r = fut.result()
            if r is not None:
                results.append(r)

    if not results:
        return pd.DataFrame(columns=[
            "scenario",
            "n_policies",
            "Total_BEL",
            "Total_RA",
            "Total_CSM_Opening",
            "Total_CSM_Closing",
            "Onerous_Count",
            "Onerous_Loss",
        ])

    return pd.DataFrame(results).sort_values("scenario").reset_index(drop=True)
