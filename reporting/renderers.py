from rest_framework.renderers import JSONRenderer


class PDFDownloadRenderer(JSONRenderer):
    """Admitir PDF; el archivo usa HttpResponse y DRF renderiza errores/metadatos."""

    media_type = "application/pdf"
    format = "pdf"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # Errores y OPTIONS mantienen su contrato JSON aunque se solicite PDF.
        renderer_context["response"]["Content-Type"] = "application/json"
        return super().render(data, accepted_media_type, renderer_context)
