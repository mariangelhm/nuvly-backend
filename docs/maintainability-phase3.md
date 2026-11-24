# Fase 3: mantenibilidad y legibilidad

Fecha: 2026-11-24. Refactorización local verificada; no se accedió a una base real ni se desplegó.

## Responsabilidades del backend

El antiguo módulo domain/services.py queda como punto de importación compatible. Las implementaciones se organizan así:

| Módulo | Responsabilidad |
| --- | --- |
| domain/configs.py | Configuraciones inmutables de colecciones, tipos y entidades. |
| domain/commercial_rules.py | Reglas de disponibilidad de componentes, variantes y extras. |
| domain/template_service.py | Ciclo de vida de templates: crear, editar y publicar. |
| domain/customer_project_service.py | Propiedad, edición, publicación y ciclo de vida de proyectos del cliente. |
| domain/project_support.py | Proyección de respuestas, URLs de media e historial de estados compartidos. |
| domain/services.py | Reexportaciones para conservar las importaciones existentes. |

La lógica de los servicios se conserva, incluyendo filtros de propiedad, revisión CAS, snapshots, cuotas y verificación de pago. Los tests que sustituyen reloj/configuración apuntan ahora al módulo donde vive la implementación. Los loggers de templates y proyectos identifican su propio módulo.

## Responsabilidades del frontend

- **invitationSections.js:** identidad de secciones, aliases y orden compartidos entre StudioWorkspace y useStudioComposerPreviewModel. El editor conserva la posición de secciones desactivadas; el preview calcula su orden sobre las visibles. Esta diferencia queda explícita mediante includeDisabled.
- **previewEvaluation.js:** parsing y reglas de formularios de evaluación, sin dependencia de Vue ni navegación.
- **usePreviewEvaluations.js:** estado reactivo de evaluaciones y wizard por instancia de preview. Recibe resolución de contenido y navegación como dependencias explícitas. No persiste los formularios de demostración en la API.
- **previewDashboard.js:** parsing y presentación de datos del dashboard, sin estado ni router.
- **useWorkspaceUiState.js:** persistencia/restauración de preferencias visuales por proyecto. Si sessionStorage falla, la edición continúa en memoria y se registra una advertencia; el contenido del proyecto sigue en store/API.
- **StudioComposerPreview.css y StudioWorkspace.css:** estilos externos cargados con style scoped src. Se conservan selectores, orden de reglas y alcance de Vue. Los componentes mantienen la composición de interfaz y eventos.

StudioComposerPreview.vue queda en 5.350 líneas de fuente y StudioWorkspace.vue en 5.952. La reducción separa estilos y lógica con responsabilidades propias; no implica menor tamaño del bundle ni que toda la composición visual se haya vuelto pequeña. Los estilos y las interfaces extensas siguen siendo candidatos a extracciones por funcionalidad cuando se modifiquen esas áreas, protegidas por las mismas regresiones.

## Verificación

- Backend: **454 pruebas offline aprobadas**. Se ejecutaron las regresiones existentes de permisos, pagos, publicación, concurrencia, privacidad y round-trip después de separar los módulos.
- Frontend: **132 casos unitarios + 103 regresiones aprobados**. Incluyen cuatro casos nuevos de orden visible/desactivado, aislamiento de estado, confirmación de descarte, validación del wizard y almacenamiento no disponible.
- **Build de producción aprobado.**
- Chrome headless: **seis casos inline aprobados** (cliente y Studio; hero, footer y footer duplicado), preservando selección, visibilidad, caret y posición del preview.
- Chrome headless responsive: **nueve casos / 72 vistas**, anchos de 320 a 1440 px, sin errores de componentes, overflow ni texto recortado. Es una muestra de footers y del preset de construcción; no una certificación de todos los diseños. Evidencia en `../../wedding_invitations_catalog/docs/qa/mobile-layout/phase3-responsive.json` dentro del workspace.

El test inline ahora espera document.fonts.ready y el fin real de las transiciones del acordeón; el retardo fijo anterior comprobaba geometría intermedia y fallaba también al restaurar los estilos inline. Se toleran dos píxeles CSS de redondeo nativo al colocar el caret, manteniendo la comprobación de desplazamiento del preview.

Las comprobaciones de código fuente de estilos leen también el CSS externo. Las comprobaciones del orden de invitaciones usan la función compartida en vez de exigir que su implementación permanezca copiada dentro del componente.

## Continuación

Fase 4: calidad automática (lint, formato, comprobación de tipos y CI). Fase 5: validación operativa con infraestructura, datos y dominios reales. Las advertencias previas de deprecación HTTP 422 siguen registradas para la fase 4.
