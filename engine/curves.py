from typing import Tuple
import numpy as np
import pandas as pd
import logging
from model.config_model import ModelConfig

logger = logging.getLogger(__name__)


def validate_config(config: ModelConfig) -> None:
    """
    Config parametrelerini IFRS17 standartlarına göre valide et.

    Raises:
        ValueError: Hatalı config parametresi
    """

    # Config parametrelerini valide et
    if config.discount_rate < 0 or config.discount_rate > 1:
        raise ValueError(f"discount_rate [0, 1] aralığında olmalı, {config.discount_rate} verildi")

    # Senaryo şoku varsa efektif oranı da kontrol et
    shift = float(getattr(config, "discount_rate_shift", 0.0) or 0.0)
    effective_rate = float(config.discount_rate) + shift
    if effective_rate <= -0.999:
        raise ValueError(f"discount_rate_shift çok büyük negatif: effective_rate={effective_rate}")

    # Coc ratio genelde %6 civarında olur, ancak sınırları esnetebiliriz
    if config.coc_ratio < 0 or config.coc_ratio > 1:
        raise ValueError(f"coc_ratio [0, 1] aralığında olmalı, {config.coc_ratio} verildi")

    # Confidence level genelde %75 civarında olur, ancak sınırları esnetebiliriz
    if config.confidence_level < 0.5 or config.confidence_level > 1:
        raise ValueError(
            f"confidence_level [0.5, 1] aralığında olmalı, {config.confidence_level} verildi"
        )

    # Tax rate genelde %0-30 arasında olur, ancak sınırları esnetebiliriz
    if config.tax_rate < 0 or config.tax_rate > 1:
        raise ValueError(f"tax_rate [0, 1] aralığında olmalı, {config.tax_rate} verildi")

    # Projection years genelde 10-30 yıl arasında olur, ancak sınırları esnetebiliriz
    if config.projection_years <= 0:
        raise ValueError(f"projection_years > 0 olmalı, {config.projection_years} verildi")

    # Lapse oranı genelde %0-20 arasında olur, ancak sınırları esnetebiliriz
    if config.lapse_base_rate < 0 or config.lapse_base_rate > 1:
        raise ValueError(
            f"lapse_base_rate [0, 1] aralığında olmalı, {config.lapse_base_rate} verildi"
        )

    # Lapse decay genelde 0-0.5 arasında olur, ancak sınırları esnetebiliriz
    if config.lapse_decay < 0:
        raise ValueError(f"lapse_decay >= 0 olmalı, {config.lapse_decay} verildi")


def tax_adjusted_discount_factor(config: ModelConfig) -> float:
    """
    IFRS17 standardına uygun iskonto faktörü.

    Vergi uygulaması: IFRS17'de BEL'in PV'si hesaplanırken vergi uygulanmaz.
    Vergi etkisi RA'ya yansır.

    Formula:
        v = 1 / (1 + i)

    Args:
        config: ModelConfig nesnesi

    Returns:
        float: Yıllık iskonto faktörü (0 ile 1 arasında)

    Raises:
        ValueError: Config geçersizse
    """

    # Config'u valide et
    validate_config(config)
    shift = float(getattr(config, "discount_rate_shift", 0.0) or 0.0)
    effective_rate = float(config.discount_rate) + shift
    return 1 / (1 + effective_rate)


def create_discount_curve(config: ModelConfig) -> pd.DataFrame:
    """
    IFRS17 uyumlu iskonto eğrisi oluştur.

    Eğri açıklaması:
    - Year: Yıl numarası (1 den projection_years'e kadar)
    - discount_factor: Dönem sonundaki indirim faktörü = v^t
    - discount_factor_opening: Dönem başındaki indirim faktörü = v^(t-1)

    Opening factor kullanımı:
    - Yılın başında oluşan nakit akışları (primler) için
    - Yılın sonunda oluşan nakit akışları (fayda) için closing factor

    Args:
        config: ModelConfig nesnesi

    Returns:
        pd.DataFrame: Iskonto faktörleri tablosu

    Raises:
        ValueError: Config geçersizse
    """

    # Config'u valide et
    validate_config(config)

    # İskonto faktörünü hesapla
    years = np.arange(1, config.projection_years + 1)

    # Vergi etkisi RA'ya yansır, iskonto faktörüne değil
    v = tax_adjusted_discount_factor(config)

    # İskonto eğrisi oluştur
    discount_curve = pd.DataFrame(
        {
            "Year": years.astype(np.int32),
            "discount_factor": (v**years).astype(np.float32),
            "discount_factor_opening": (v ** (years - 1)).astype(np.float32),
        }
    )

    # İskonto eğrisi oluşturulduğunda logla
    logger.debug(f"✓ Iskonto eğrisi oluşturuldu: {len(discount_curve)} yıl")

    return discount_curve  # İskonto eğrisi tablosuna içeri aktarır.


# Lapse eğrisi oluşturma
def get_exponential_lapse(years: np.ndarray, initial_rate: float, decay: float) -> np.ndarray:
    """
    Üssel azalan lapse oranı hesapla.

    Not: Bu fonksiyon basit bir "exponential decay" yaklaşımıdır.
    Bazı ürünlerde ilk yıllarda lapse daha yüksek olabilir (front-loaded),
    bazı ürünlerde ise daha düşük olabilir. Bu nedenle `initial_rate` ve
    `decay` parametreleri ürün davranışına göre kalibre edilmelidir.

    Bu formül tercih edilirse, decay parametresi şu anlama gelir:
    - decay = 0: sabit lapse (initial_rate)
    - decay > 0: azalan lapse (ilk yıl initial_rate, sonra düşer)
    - decay = 0.1: moderasyon (10% yıllık düşüş)

    Formula:
        lapse_t = l0 * exp(-k * (t - 1))

    Clipping Mantığı: [0, 1] aralığına getirme
    - Negatif değerler: matematiksel hata koruması
    - 1'den büyükler: gerçekçi olmayan lapse (>%100)
    - Sonuç: 0 ile 1 arasında mantıklı oranlar

    Args:
        years: Yıl dizisi (np.arange(1, n+1))
        initial_rate: İlk yıl lapse oranı [0, 1]
        decay: Azalma hızı (exponential decay parameter) [0, 1]
               - decay=0: sabit lapse
               - decay=0.5: yıllık %50 düşüş
               - decay=1.0: ilk yıldan sonra neredeyse 0

    Returns:
        np.ndarray: Her yıl için lapse oranları [0, 1] aralığında (float32)

    Raises:
        ValueError: Parametreler geçersizse

    Examples:
        >>> years = np.array([1, 2, 3, 4, 5])
        >>> lapse = get_exponential_lapse(years, initial_rate=0.15, decay=0.2)
        >>> print(lapse)  # [0.15, 0.123, 0.100, 0.082, 0.067]
    """

    # Girdi doğrulaması
    if not isinstance(years, np.ndarray) or years.ndim != 1:
        raise ValueError("years numpy 1D array olmalı")

    if initial_rate < 0 or initial_rate > 1:
        raise ValueError(f"initial_rate [0, 1] aralığında olmalı, {initial_rate} verildi")

    if decay < 0 or decay > 1:
        raise ValueError(f"decay [0, 1] aralığında olmalı, {decay} verildi")

    if np.any(years < 1):
        raise ValueError("years dizisi 1'den başlamalı")

    # Lapse oranı hesapla
    lapse = initial_rate * np.exp(-decay * (years - 1))

    # Clipping: [0, 1] aralığına getir
    # Mantık:
    #   - Negatif değerler: exponential decay uzun dönemde çok küçük olabilir
    #   - 1'den büyükler: matematiksel hata veya config hatasından kaynaklanabilir
    #   - Sonuç: [0, 1] aralığında gerçekçi lapse oranları

    # Lapse oranlarını 0 ile 1 arasında tutmak için clipping yap
    lapse_clipped = np.clip(lapse, 0, 1)

    return lapse_clipped.astype(np.float32)  # Lapse oranlarını float32 formatında döndürür.


# Lapse eğrisi oluşturma
def create_lapse_curve(config: ModelConfig) -> pd.DataFrame:
    """
    Proje periyodu için lapse eğrisi oluştur.

    Lapse oranı: poliçe sahibinin sözleşmeyi feshetme/terk etme olasılığı.

    IFRS17 uygulamasında:
    - Lapse de facto teminat süresi azaltır (CSM release etkiler)
    - Mortalite ile berberce düşünülmeli

    Args:
        config: ModelConfig nesnesi

    Returns:
        pd.DataFrame: Yıllar ve lapse oranları (float32)

    Raises:
        ValueError: Config geçersizse
    """

    # Config'u valide et
    validate_config(config)

    # Lapse eğrisi oluşturmak için yılları ve parametreleri hazırla
    years = np.arange(1, config.projection_years + 1)
    lapse_rates = get_exponential_lapse(
        years, initial_rate=config.lapse_base_rate, decay=config.lapse_decay
    )

    # Lapse eğrisi tablosu oluştur
    lapse_curve = pd.DataFrame({"Year": years.astype(np.int32), "lapse_rate": lapse_rates})

    # Lapse eğrisi oluşturulduğunda logla
    logger.debug(f"✓ Lapse eğrisi oluşturuldu: {len(lapse_curve)} yıl")

    return lapse_curve  # Lapse eğrisi tablosuna içeri aktarır.


# Tüm eğrileri birleştirme
def create_full_curve_table(config: ModelConfig) -> pd.DataFrame:
    """
    Discount ve lapse eğrilerini birleştir.

    Returns:
        pd.DataFrame: Tüm eğri faktörleri bir tabloda
    """

    # İskonto ve lapse eğrilerini oluştur
    discount_curve = create_discount_curve(config)

    # Lapse eğrisi oluştur
    lapse_curve = create_lapse_curve(config)

    # Eğrileri Year sütununa göre birleştir
    full_curve = discount_curve.merge(lapse_curve, on="Year", how="inner")

    return full_curve  # Tüm eğri faktörlerini tek bir DataFrame'de birleştirir.
