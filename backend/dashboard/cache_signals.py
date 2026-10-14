from django.db.models.signals import post_delete, post_save

from common.data_cache import invalidate_shared_data
from countries.models import Moneda, Pais
from economics.models import IndicadorEconomico, TipoIndicador
from risk.models import IndiceRiesgo


def changed(sender, using, **kwargs):
    invalidate_shared_data(using=using)


for model in (Moneda, Pais, TipoIndicador, IndicadorEconomico, IndiceRiesgo):
    for signal in (post_save, post_delete):
        signal.connect(changed, sender=model, weak=False,
                       dispatch_uid=f'data_cache:{model._meta.label}:{id(signal)}')
