# Pocket Notebook Evidence

This document indexes selected pages from the founder's undated pocket
notebook. The founder recalls using it during late-May architecture planning
and early clinic observation in June 2026.

The pages contain product questions, workflow logic, architecture sketches,
and early hypotheses. They contain no patient records, credentials, OAuth
tokens, or Google Workspace data. Exact chronology is supported by dated
digital planning files; the notebook itself should not be presented as dated
evidence.

The notebook also records AI-assisted learning. The founder did not enter the
project with formal software-engineering training. Gemini, ChatGPT, Cursor, and
later OpenAI Codex were used to explain unfamiliar concepts, compare possible
approaches, and support implementation. The founder rewrote those explanations
as questions and sketches he could reason about, then decided what to apply,
test, constrain, or reject based on direct clinic observation. These pages
therefore document both product reasoning and the practical learning process
enabled by AI.

## How to read this evidence

The handwriting and crossed-out ideas are intentionally preserved. They show
the product-development method used for Doko:

1. Ask an operational question.
2. Use AI to clarify unfamiliar technical concepts when needed.
3. Rewrite the explanation as a workflow or sketch the founder could evaluate.
4. Observe the clinic.
5. Test the idea.
6. Keep, constrain, or discard it.

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
hold, edit, search, confirm, and release workflows in the production medical
panel.

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

> This pocket notebook was used to turn operational questions into testable
> workflows. Some ideas became production features, some were constrained by
> privacy and safety rules, and others were discarded after direct clinic
> observation. The dated digital specifications in this repository establish
> the project timeline. The notebook documents how the founder used AI to learn
> unfamiliar technical concepts, translated them into understandable sketches,
> and tested the resulting decisions against real clinic operations.

## Publication checklist

- Use no more than six notebook images in the public gallery.
- Rotate and crop each image for readability without removing crossed-out text.
- Do not add invented dates to individual pages.
- Fully exclude the original third-party branding on the notebook cover.
- Keep Spanish handwriting visible and place the English translation in the
  caption or adjacent evidence document.
- Recheck every selected image for patient names, contact details, credentials,
  tokens, and Google Workspace data before publishing.
