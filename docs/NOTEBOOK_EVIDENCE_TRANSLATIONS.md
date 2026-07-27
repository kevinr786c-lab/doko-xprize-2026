# Pocket Notebook Evidence

Este documento reúne páginas seleccionadas de mi libreta de bolsillo sin fecha.
Recuerdo haberla usado durante la planeación de arquitectura de finales de
mayo y la observación inicial en consultorios durante junio de 2026.

The pages contain product questions, workflow logic, architecture sketches,
and early hypotheses. They contain no patient records, credentials, OAuth
tokens, or Google Workspace data. Exact chronology is supported by dated
digital planning files; the notebook itself should not be presented as dated
evidence.

La libreta también registra mi aprendizaje apoyado por IA. No inicié el
proyecto con formación formal en ingeniería de software. Usé Gemini, ChatGPT,
Cursor y después OpenAI Codex para entender conceptos, comparar alternativas y
apoyar la implementación. Reescribí esas explicaciones como preguntas y
dibujos que pudiera razonar; después decidí qué aplicar, probar, limitar o
descartar con base en la observación directa del consultorio. Estas páginas
documentan tanto el razonamiento del producto como el aprendizaje práctico que
la IA hizo posible.

## How to read this evidence

The handwriting and crossed-out ideas are intentionally preserved. They show
the product-development method used for Doko:

1. Me hago una pregunta operativa.
2. Uso IA para aclarar conceptos técnicos que todavía no conozco.
3. Convierto la explicación en un flujo o dibujo que pueda evaluar.
4. Observo el consultorio.
5. Pruebo la idea.
6. La conservo, la limito o la descarto.

The English text below is a faithful explanatory translation, not a literal
claim that every early idea became part of the production product.

## Selected public pages

### 1. Early hybrid architecture

**Source image:** [01-hybrid-architecture.jpeg](evidence/notebook/01-hybrid-architecture.jpeg)

**Spanish transcription:**

> Base de datos. SQL. Agentes. Calendario y Gmail. Llenado manual. Index.
> App-Elite. Se llenan con información de doctora. Llenado automático.

**English translation:**

> Early architecture sketch connecting a SQL database, agents, Calendar and
> Gmail, the application, and both manual and automated data flows. Clinic
> information would populate the system while deterministic application flows
> coordinated the operational layers.

**What it demonstrates:** The hybrid architecture was considered before the
final implementation: structured data and application rules remain the source
of truth, while AI assists only in bounded tasks.

### 2. Removing laboratory-result uploads

**Source image:** [02-remove-lab-results.jpeg](evidence/notebook/02-remove-lab-results.jpeg)

**Spanish transcription:**

> Quitar la función de subir los resultados del laboratorio. Mejor mandar
> correo de notificación, etc.

**English translation:**

> Remove the feature for uploading laboratory results. Prefer a notification
> workflow instead.

**What it demonstrates:** Doko deliberately reduced its clinical-data scope.
The product focused on clinic operations rather than collecting medical files
that were not necessary for the service.

### 3. From an autonomous scheduler to controlled assistance

**Source image:** [03-controlled-scheduling.jpeg](evidence/notebook/03-controlled-scheduling.jpeg)

**Spanish transcription:**

> Agente agendador que se pueda cancelar y confirmar de ahí mismo, también
> reagendar. Tomar información del paciente junto a resultados y mandar correo
> con resultados.

**English translation:**

> Early scheduler-agent idea: cancel, confirm, and reschedule from one place.
> The same note also considered collecting patient information and emailing
> results.

**What it demonstrates:** Only the operational appointment actions survived.
Clinical-result handling was discarded, and production actions were placed
behind deterministic validation and human confirmation.

### 4. Clinic profile as a shared source

**Source image:** [04-shared-clinic-profile.jpeg](evidence/notebook/04-shared-clinic-profile.jpeg)

**Spanish transcription:**

> Doko Elite. Agregar para que el doctor pueda poner su nombre, teléfono,
> instrucciones, servicios, precios, horarios por defecto, dar instrucciones de
> correo, mapa, ubicación y responder.

**English translation:**

> Allow the doctor to configure a public name, phone number, instructions,
> services, prices, default hours, email guidance, map, and location.

**What it demonstrates:** This became the shared clinic profile that now feeds
the patient portal, public medical page, and bounded patient assistant without
duplicating the same information in separate systems.

### 5. Calendar operations before the final panel

**Source image:** [05-calendar-operations.jpeg](evidence/notebook/05-calendar-operations.jpeg)

**Spanish transcription:**

> Calendario proporciona horarios de citas, información de contacto, nombre,
> apellido, dirección de correo y número de teléfono. Se pueden editar horas,
> bloquear horas, cambiar duración y descripción.

**English translation:**

> Calendar provides appointment times and contact information. The operational
> interface should support editing time, blocking time, changing duration, and
> updating the description.

**What it demonstrates:** These notes became the appointment, block, temporary
hold, edit, search, confirm, release, and cancellation workflows in the
production medical panel.

### 6. Doko Suffy structured catalog

**Source image:** [06-suffy-catalog.jpeg](evidence/notebook/06-suffy-catalog.jpeg)

**Spanish transcription:**

> Tienda. Catálogo de producto maestro: nombre comercial, marca, registro
> sanitario, unidad de venta, clase de riesgo, requiere estéril, especialidad,
> galería o foto y precio de venta. Descripción y características.

**English translation:**

> Doko Suffy master-product catalog: commercial name, brand, sanitary
> registration, sales unit, risk class, sterile status, specialty, image
> gallery, sale price, description, and product characteristics.

**What it demonstrates:** Suffy was designed as a structured B2B supply
operation rather than a generic public online store.

## Reserve pages

The following pages are useful as supporting evidence but should not compete
with the six primary images on the public project page:

- A real Suffy persistence problem where a sterile/non-sterile change appeared
  in the interface but was not saved correctly.
- Early order, subtotal, tax, payment, status, tracking, and GPS concepts.
- Early table lists for doctors, OAuth tokens, appointment radar, inventory,
  lots, suppliers, and orders.
- A login note describing Google OAuth as difficult to use. This records a
  learning and usability question, not prior OAuth expertise. It later led to
  separating Doko's internal sign-in from the explicit `Connect Google` flow.
- Patient portal concepts for services, prices, iframe scheduling, frequently
  asked questions, and first-visit guidance.
- A broader services list that was intentionally narrowed to avoid medication
  recommendations and other unsafe or premature functions.

## Caption for the public project

> Usé esta libreta para convertir preguntas operativas en flujos que pudiera
> probar. Algunas ideas se volvieron funciones de producción, otras quedaron
> limitadas por privacidad y seguridad, y otras las descarté después de
> observar el consultorio. Las especificaciones digitales con fecha establecen
> la línea de tiempo del proyecto. La libreta muestra cómo usé IA para aprender
> conceptos técnicos, convertirlos en dibujos comprensibles y probar las
> decisiones contra operaciones reales.

## Publication checklist

- Use no more than six notebook images in the public gallery.
- Rotate and crop each image for readability without removing crossed-out text.
- Do not add invented dates to individual pages.
- Fully exclude the original third-party branding on the notebook cover.
- Keep Spanish handwriting visible and place the English translation in the
  caption or adjacent evidence document.
- Recheck every selected image for patient names, contact details, credentials,
  tokens, and Google Workspace data before publishing.
