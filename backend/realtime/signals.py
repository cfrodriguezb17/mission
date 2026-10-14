from django.db.models.signals import post_save
from django.dispatch import receiver

from alerts.models import Alerta
from countries.models import Pais
from economics.models import IndicadorEconomico
from risk.models import IndiceRiesgo
from .events import publish


@receiver(post_save, sender=Alerta, dispatch_uid='realtime.alert.created')
def alert_created(sender, instance, created, using, **kwargs):
    if created:
        group = 'alerts.global' if instance.usuario_id is None else f'alerts.user.{instance.usuario_id}'
        publish(group, {'kind': 'alert', 'id': instance.pk}, using=using)


@receiver(post_save, sender=IndiceRiesgo, dispatch_uid='realtime.risk.changed')
@receiver(post_save, sender=Pais, dispatch_uid='realtime.country.changed')
@receiver(post_save, sender=IndicadorEconomico, dispatch_uid='realtime.indicator.changed')
def dashboard_changed(sender, instance, using, **kwargs):
    publish('dashboard', {'kind': 'dashboard'}, using=using)
