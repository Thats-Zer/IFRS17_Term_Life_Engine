# YEDEK - Eski diskonto faktörü formülü (YANLIŞ)
# Bu dosya sadece referans için saklanmıştır

def tax_adjusted_discount_factor_OLD(config) -> float:
    """
    YANLIŞ FORMÜL - Bu dosya referans içindir
    
    Vergi sonrası iskonto faktörü (HATALI):
    v = 1 / (1 + i * (1 - tax_rate))
    
    Neden yanlış?
    - IFRS17'de vergi bu şekilde uygulanmaz
    - BEL hesaplanırken vergi etkisi dikkate alınmaz
    - Vergi etkisi RA (Risk Adjustment) bileşenine yansır
    
    Doğru formül:
    v = 1 / (1 + i)  ← Kullanılan formül
    """
    return 1 / (1 + config.discount_rate * (1 - config.tax_rate))