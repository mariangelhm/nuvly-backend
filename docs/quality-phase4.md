# Fase 4: calidad automática y CI

Fecha: 2026-11-24. Controles implementados y ejecutados localmente. Los workflows se ejecutarán en GitHub al próximo push o pull request; todavía no hay una ejecución remota de estos cambios.

## Comandos reproducibles

Frontend (Node 22):

```powershell
npm ci --ignore-scripts
npm run check
```

`check` detiene la cadena ante el primer fallo: lint, formato, tipos, pruebas y build. También existen `npm run lint`, `npm run lint:fix`, `npm run format:check`, `npm run format:fix` y `npm run typecheck`.

Backend (entorno Python 3.14.5 activo):

```powershell
python -m pip install -r requirements-dev.txt
python scripts/check_quality.py --tests
```

Con el venv del workspace en Windows se puede usar `.\.venv\Scripts\python.exe` en lugar de `python`. Si ese entorno fue creado con uv sin pip, instalar con `uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt`.

El script ejecuta Ruff lint, Ruff format --check y mypy; `--tests` añade la suite offline sin acceso a red. Las comprobaciones no modifican el código. Las correcciones locales se aplican explícitamente con `python -m ruff check --fix app scripts tests` y `python -m ruff format app scripts tests`.

## Alcance real de los controles

| Control | Alcance |
| --- | --- |
| ESLint + Vue + parser TypeScript | Todo src, tests, scripts del frontend y configuraciones JS. Cero warnings permitidos. |
| Ruff lint | Todo app, scripts y tests del backend; reglas E4/E7/E9/F e imports ordenados. |
| Ruff formato | Todo app, scripts y tests: 127 archivos comprobados en esta verificación. |
| mypy strict | Ocho módulos de contratos: tipos de valor, catálogo, configuración de entidades, estados y schemas de dominio, precios, pagos y descuentos. |
| vue-tsc | Siete bloques Vue con script TypeScript, su hook useCountdown.ts y cuatro utilidades JS de contratos con @ts-check. |
| Prettier | 23 archivos enumerados explícitamente en quality/format-files.json: configuración, utilidades compartidas, composables y bloques tipados. |
| Regresiones | 454 pruebas backend; 132 casos unitarios + 103 regresiones frontend; build de producción. |

La adopción de tipos y formato del frontend es incremental. La mayor parte de los servicios/stores JS y de los componentes heredados todavía no tiene comprobación estricta de tipos ni formato Prettier obligatorio. Sí pasan el lint completo. El formato y los tipos deben ampliarse agregando archivos a los manifiestos/configuraciones y corrigiendo los problemas detectados; estos controles no certifican que todo el proyecto sea estrictamente tipado.

Los cuatro contratos JS comprobados son invitationSections.js, previewDashboard.js, invitationWritePayload.js y paymentRedirect.js. `tests/types/contracts.ts` contiene cuatro casos negativos con @ts-expect-error: proveedores desconocidos, testMode textual, payload no objeto y visibilidad no booleana. Si esos contratos se vuelven demasiado amplios, el compilador detecta que el error esperado desapareció y falla.

Mypy usa follow_imports=silent para comprobar los ocho módulos declarados sin atribuir cobertura estricta a las implementaciones dinámicas importadas. Existe una exclusión puntual prop-decorator para el descriptor computed_field de Pydantic. Las únicas excepciones Ruff E402 corresponden a cuatro entry points que preparan path/entorno antes de importar la aplicación. ESLint conserva una lista explícita de nombres de componentes heredados para la regla multi-word-component-names y permite parámetros con prefijo _ cuando se retienen por compatibilidad.

## Correcciones realizadas

- Import de parsePairs ausente en StudioWorkspace, que podía fallar al resolver colecciones dinámicas.
- Eliminación de imports y declaraciones sin uso. Se conservan llamadas de inicialización con posibles efectos y se mantienen los argumentos de compatibilidad.
- Eliminación de return dentro de finally en StudioNew: solo se actualiza el estado de la solicitud vigente, sin ocultar excepciones de una solicitud anterior.
- Conservación de cause al traducir errores de subida de imágenes; eliminación de inicializaciones inmediatamente sobrescritas.
- Props configurables tipadas como Record<string, unknown> con conversión explícita en los consumidores. El manejador de imagen rota comprueba HTMLImageElement antes de acceder a style.
- Contratos compartidos tipados con JSDoc y schemas Pydantic declarando sus campos comunes. El formato Python y el orden de imports son uniformes.
- Sustitución de HTTP_422_UNPROCESSABLE_ENTITY por HTTP_422_UNPROCESSABLE_CONTENT: conserva el código 422 y elimina las advertencias de deprecación observadas.
- Servidores Vite de pruebas SSR con HMR y su canal WebSocket deshabilitados, evitando conflictos de puertos entre pruebas paralelas; ruta inicial explícita en el fixture de retorno de checkout.

## CI y dependencias

Ambos workflows tienen permiso contents:read, timeout de 15 minutos y cancelación de ejecuciones anteriores de la misma rama/workflow. Frontend instala con npm ci --ignore-scripts y ejecuta npm run check. Backend instala requirements-dev.txt con constraints, ejecuta pip check, el script de calidad y las pruebas offline. Las herramientas nuevas están fijadas en package-lock.json y requirements-dev-lock.txt; Ruff/mypy son dependencias de desarrollo.

Los workflows no despliegan ni realizan pagos. Las pruebas de navegador se ejecutaron localmente con Chrome headless y fixtures; no se añadieron como job Linux en esta fase. La ejecución de CI en GitHub y la validación con infraestructura real siguen pendientes.

## Evidencia local

- Backend: lint, formato y mypy aprobados; 454 pruebas aprobadas sin advertencias. Las 57 dependencias instaladas también pasan uv pip check.
- Frontend: lint sin warnings, formato de los 23 archivos, vue-tsc, 235 pruebas y build aprobados.
- Chrome headless: seis casos de edición inline aprobados, incluyendo bloques duplicados en cliente y Studio.
- Responsive: 32 casos / 256 vistas entre 320 y 1440 px, sin errores de componentes, overflow ni texto recortado. Reporte: `../../wedding_invitations_catalog/docs/qa/mobile-layout/phase4-responsive.json` dentro del workspace.

## Referencias de configuración

[ESLint: flat config](https://eslint.org/docs/latest/use/configure/configuration-files), [Ruff: configuración](https://docs.astral.sh/ruff/configuration/), [TypeScript: opciones de compilación](https://www.typescriptlang.org/tsconfig/).

Siguiente fase: validación operativa en staging (Mongo, datos heredados, dominios/cookies, pagos, almacenamiento y restauración).
