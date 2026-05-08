import sys
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from engine.asumptions import loadconfig
from engine.curves import create_discount_curve
from engine.projection import (
    create_master_data,
    create_projection_table,
    load_mortality_table
)
from engine.cashflows import calculate_cashflows
from engine.bel import calculate_bel
from engine.ra import calculate_risk_adjustment
from engine.csm import calculate_csm_rollforward
from engine.grouping import assign_ifrs17_groups
from engine.outputs import save_outputs
from engine.scenarios import run_scenarios

# ==================================================
# LOGGING CONFIGURATION
# ==================================================

def _configure_console_encoding() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

_configure_console_encoding()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("engine.log", encoding="utf-8", mode="w"),  # <-- önemli: mode="w"
    ],
    force=True,
)
logger = logging.getLogger(__name__)


# ==================================================
# ERROR HANDLING
# ==================================================

class EngineException(Exception):
    """IFRS17 Engine custom exception."""
    pass


def handle_error(step_name: str, error: Exception) -> None:
    """
    Hata yönetimi ve logging.
    
    Args:
        step_name: Adım adı
        error: Exception objesi
    """
    logger.error(
        f"✗ HATA ADIM {step_name}: {type(error).__name__}: {str(error)}",
        exc_info=True
    )


def validate_config(config) -> bool:
    """
    Config parametrelerini doğrula.
    
    Returns:
        bool: Geçerli ise True
        
    Raises:
        ValueError: Geçersiz parameter
    """
    if config.n_policies <= 0:
        raise ValueError("n_policies > 0 olmalı")
    if config.projection_years <= 0:
        raise ValueError("projection_years > 0 olmalı")
    if config.discount_rate < 0 or config.discount_rate > 1:
        raise ValueError("discount_rate [0, 1] aralığında olmalı")
    
    logger.info("OK Config validated")
    return True


# ==================================================
# MAIN ENGINE
# ==================================================

def main() -> None:
    """
    IFRS17 Term Life Engine ana akışı.
    
    Adımlar:
    1. Config yükleme
    2. Master data oluşturma
    3. Projection oluşturma
    4. Nakit akışları hesaplama
    5. BEL hesaplama
    6. RA hesaplama
    7. CSM rollforward
    8. Gruplandırma
    9. Senaryo analizi
    10. Çıktı kaydetme
    """
    
    success = False
    try:
        logger.info("=" * 70)
        logger.info("IFRS17 TERM LIFE ENGINE BAŞLANIYOR")
        logger.info("=" * 70)
        
        # ==================================================
        # STEP 1: CONFIG
        # ==================================================
        
        try:
            logger.info("1. Config yükleniyor...")
            config = loadconfig("config/config.json")
            validate_config(config)
        except Exception as e:
            handle_error("CONFIG", e)
            raise EngineException(f"Config yönetimi başarısız: {e}")
        
        # ==================================================
        # STEP 2: MORTALITY TABLE
        # ==================================================
        
        mortality_table = None
        if config.use_mortality_table:
            try:
                logger.info("2. Mortalite tablosu yükleniyor...")
                mortality_table = load_mortality_table(config.mortality_table_path)
            except Exception as e:
                logger.warning(f"⚠️ Mortalite tablosu yüklenemedi: {e}")
                mortality_table = None
        
        # ==================================================
        # STEP 3: MASTER DATA
        # ==================================================
        
        try:
            logger.info("3. Master data oluşturuluyor...")
            master_data = create_master_data(config)
        except Exception as e:
            handle_error("MASTER_DATA", e)
            raise EngineException(f"Master data oluşturulamadı: {e}")
        
        # ==================================================
        # STEP 4: DISCOUNT CURVE
        # ==================================================
        
        try:
            logger.info("4. Discount curve oluşturuluyor...")
            discount_curve = create_discount_curve(config)
        except Exception as e:
            handle_error("DISCOUNT_CURVE", e)
            raise EngineException(f"Discount curve oluşturulamadı: {e}")
        
        # ==================================================
        # STEP 5: PROJECTION
        # ==================================================
        
        try:
            logger.info("5. Projection oluşturuluyor...")
            projection = create_projection_table(master_data, config, mortality_table)
            projection = projection.merge(discount_curve, on="Year", how="left")
        except Exception as e:
            handle_error("PROJECTION", e)
            raise EngineException(f"Projection oluşturulamadı: {e}")
        
        # ==================================================
        # STEP 6: CASHFLOWS
        # ==================================================
        
        try:
            logger.info("6. Nakit akışları hesaplanıyor...")

            if "coverage_years" not in projection.columns:
                if "Year" not in projection.columns:
                    raise EngineException("Projection içinde 'Year' sütunu yok")
                projection["coverage_years"] = projection["Year"].astype(int)

            projection = calculate_cashflows(projection, config)
        except Exception as e:
            handle_error("CASHFLOWS", e)
            raise EngineException(f"Nakit akışları hesaplanamadı: {e}")
        
        # ==================================================
        # STEP 7: BEL
        # ==================================================
        
        try:
            logger.info("7. BEL hesaplanıyor...")
            bel_result = calculate_bel(projection, config)
        except Exception as e:
            handle_error("BEL", e)
            raise EngineException(f"BEL hesaplanamadı: {e}")
        
        # ==================================================
        # STEP 8: RA
        # ==================================================
        
        try:
            logger.info("8. RA hesaplanıyor...")
            ra_result = calculate_risk_adjustment(projection, config)
        except Exception as e:
            handle_error("RA", e)
            raise EngineException(f"RA hesaplanamadı: {e}")
        
        # ==================================================
        # STEP 9: CSM
        # ==================================================
        
        try:
            logger.info("9. CSM rollforward hesaplanıyor...")
            csm_result = calculate_csm_rollforward(
                bel_result,
                ra_result,
                projection,
                config
            )
        except Exception as e:
            handle_error("CSM", e)
            raise EngineException(f"CSM hesaplanamadı: {e}")
        
        # ==================================================
        # STEP 10: GROUPING
        # ==================================================
        
        try:
            logger.info("10. IFRS17 gruplandırması yapılıyor...")
            group_result = assign_ifrs17_groups(csm_result, projection, config)
        except Exception as e:
            handle_error("GROUPING", e)
            raise EngineException(f"Gruplandırma başarısız: {e}")
        
        # ==================================================
        # STEP 11: SCENARIOS
        # ==================================================
        
        try:
            if getattr(config, "run_scenarios", False):
                logger.info("11. Senaryo analizi yapılıyor...")
                # Scenarios listesi sözlük formatında değilse varsayılan sözlüğü kullan
                from engine.scenarios import SCENARIOS
                scenarios_dict = getattr(config, "scenarios", None)
                if not isinstance(scenarios_dict, dict):
                    scenarios_dict = SCENARIOS
                    
                scenario_results = run_scenarios(
                    base_config=config, 
                    scenarios=scenarios_dict, 
                    mortality_table=mortality_table
                )
            else:
                logger.info("11. Senaryo analizi devre dışı")
                scenario_results = None
        except Exception as e:
            logger.warning(f"⚠️ Senaryo analizi hatası: {e}", exc_info=True)
            scenario_results = None
        
        # ==================================================
        # STEP 12: OUTPUTS
        # ==================================================
        
        try:
            logger.info("12. Çıktılar kaydediliyor...")
            save_outputs(
                projection=projection,
                bel_result=bel_result,
                ra_result=ra_result,
                csm_result=csm_result,
                scenario_results=scenario_results,
                output_dir="outputs",
                master=master_data
            )
        except Exception as e:
            handle_error("OUTPUTS", e)
            raise EngineException(f"Çıktılar kaydedilemedi: {e}")
        
        # ==================================================
        # SUCCESS
        # ==================================================
        
        logger.info("=" * 70)
        logger.info("✓ IFRS17 ENGINE BAŞARIYLA TAMAMLANDI")
        logger.info("=" * 70)
        
        success = True

    except EngineException as e:
        logger.critical(f"✗ MOTOR HATASI: {e}")
        raise
    except Exception as e:
        logger.critical(f"✗ BEKLENMEYEN HATA: {type(e).__name__}: {e}", exc_info=True)
        raise
    finally:
        logger.info("İşlem sonlandırılıyor...")
        logging.shutdown()

        # Log tail'i sadece başarısız çalışmada bas
        if not success:
            try:
                if Path("engine.log").exists():
                    lines = Path("engine.log").read_text(encoding="utf-8", errors="replace").splitlines()
                    print("\n".join(lines[-80:]))
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("⚠️ Kullanıcı tarafından sonlandırıldı")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"✗ BEKLENMEYEN HATA: {e}", exc_info=True)
        sys.exit(1)