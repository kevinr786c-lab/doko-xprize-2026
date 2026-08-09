# Pocket Notebook Evidence

This document presents selected pages from my undated pocket notebook. I
remember using it while planning the architecture in late May and observing
early clinic operations during June 2026. The notebook itself does not prove
those dates; dated digital planning files establish the project timeline.

The pages contain product questions, workflow logic, architecture sketches,
and early hypotheses. The selected pages contain no patient records,
credentials, OAuth tokens, or Google Workspace data.

The notebook also records how AI supported my learning. I did not begin Doko
with formal software-engineering training. I used Gemini, ChatGPT, Cursor, and
later OpenAI Codex to understand concepts, compare alternatives, and support
implementation. When I could not yet explain a technical idea clearly, I drew
it. The drawing helped the AI understand my question, and the explanation
helped me decide what to apply, test, limit, or discard after observing the
clinic.

## How to read this evidence

The handwriting and crossed-out ideas are intentionally preserved. They show
the method I used to develop Doko:

1. Ask an operational question.
2. Use AI and documentation to clarify unfamiliar technical concepts.
3. Convert the explanation into a flow or drawing I can evaluate.
4. Observe the clinic.
5. Test the idea.
6. Keep it, limit it, or discard it.

The English text below explains the original Spanish notes. It does not claim
that every early idea became a production feature.

## Selected public pages

### 1. Early hybrid architecture

**Source image:** [01-hybrid-architecture.jpeg](evidence/notebook/01-hybrid-architecture.jpeg)

**Original Spanish transcription:**

> Base de datos. SQL. Agentes. Calendario y Gmail. Llenado manual. Index.
> App-Elite. Se llenan con información de doctora. Llenado automático.

**English translation and explanation:**

> Database. SQL. Agents. Calendar and Gmail. Manual entry. Index. App-Elite.
> They are populated with physician information. Automatic entry.

This is an early architecture sketch connecting structured data, agents,
Google integrations, the application, and manual and automated flows. The
final product keeps structured records and deterministic rules authoritative,
while AI assists only in bounded tasks.

### 2. Removing laboratory-result uploads

**Source image:** [02-remove-lab-results.jpeg](evidence/notebook/02-remove-lab-results.jpeg)

**Original Spanish transcription:**

> Quitar la función de subir los resultados del laboratorio. Mejor mandar
> correo de notificación, etc.

**English translation and explanation:**

> Remove the feature for uploading laboratory results. It is better to send a
> notification email instead, and so on.

This decision deliberately reduced Doko's clinical-data scope. The product
focused on clinic operations instead of collecting medical files that were not
necessary for its service.

### 3. From an autonomous scheduler idea to controlled assistance

**Source image:** [03-controlled-scheduling.jpeg](evidence/notebook/03-controlled-scheduling.jpeg)

**Original Spanish transcription:**

> Agente agendador que se pueda cancelar y confirmar de ahí mismo, también
> reagendar. Tomar información del paciente junto a resultados y mandar correo
> con resultados.

**English translation and explanation:**

> Scheduling agent that can cancel and confirm from the same place, and also
> reschedule. Collect patient information together with results and email the
> results.

The appointment-control ideas survived in a more constrained form. The
clinical-results idea was discarded, and protected appointment actions were
placed behind deterministic validation and human authorization.

### 4. Clinic profile as a shared source

**Source image:** [04-shared-clinic-profile.jpeg](evidence/notebook/04-shared-clinic-profile.jpeg)

**Original Spanish transcription:**

> Doko Elite. Agregar para que el doctor pueda poner su nombre, teléfono,
> instrucciones, servicios, precios, horarios por defecto, dar instrucciones de
> correo, mapa, ubicación y responder.

**English translation and explanation:**

> Doko Elite. Allow the physician to enter a name, phone number, instructions,
> services, prices, default hours, email guidance, map, and location, and to
> answer questions.

This became a shared clinic profile that can feed the patient portal, public
physician page, and bounded patient assistant without duplicating the same
approved information in separate systems.

### 5. Calendar operations before the final panel

**Source image:** [05-calendar-operations.jpeg](evidence/notebook/05-calendar-operations.jpeg)

**Original Spanish transcription:**

> Calendario proporciona horarios de citas, información de contacto, nombre,
> apellido, dirección de correo y número de teléfono. Se pueden editar horas,
> bloquear horas, cambiar duración y descripción.

**English translation and explanation:**

> Calendar provides appointment times, contact information, first name, last
> name, email address, and phone number. Times can be edited or blocked, and the
> duration and description can be changed.

These notes informed the appointment, block, temporary-hold, edit, search,
confirm, release, and cancellation workflows in the medical panel. Google
Calendar remains the integrated scheduling foundation.

### 6. Doko Suffy structured catalog

**Source image:** [06-suffy-catalog.jpeg](evidence/notebook/06-suffy-catalog.jpeg)

**Original Spanish transcription:**

> Tienda. Catálogo de producto maestro: nombre comercial, marca, registro
> sanitario, unidad de venta, clase de riesgo, requiere estéril, especialidad,
> galería o foto y precio de venta. Descripción y características.

**English translation and explanation:**

> Store. Master product catalog: commercial name, brand, sanitary registration,
> sales unit, risk class, whether sterility is required, specialty, gallery or
> photo, and sale price. Description and characteristics.

This shows that Doko Suffy was conceived as a structured medical-supply
sourcing and fulfillment capability, not as an unrelated public online store.

## Reserve pages

The following pages may support the project history but should not compete with
the six primary images on the public project page:

- A real Suffy persistence problem in which a sterile or non-sterile change
  appeared in the interface but was not stored correctly.
- Early order, subtotal, tax, payment, status, tracking, and GPS concepts.
- Early table lists for physicians, OAuth tokens, appointment radar, Doko Suffy
  inventory and lots, suppliers, and orders.
- A login note describing Google OAuth as difficult to use. It records a
  learning and usability question, not prior OAuth expertise. It later informed
  the separation between Doko's internal sign-in and the explicit `Connect
  Google` flow.
- Patient-portal concepts for services, prices, embedded scheduling, frequently
  asked questions, and first-visit guidance.
- A broader services list that was intentionally narrowed to avoid medication
  recommendations and other unsafe or premature functions.

## Suggested public caption

> I used this pocket notebook to turn operational questions into flows I could
> test. Some ideas became production features, some were limited for privacy or
> safety, and others were discarded after observing the clinic. Dated digital
> specifications establish the project timeline; the notebook shows how I used
> AI to learn technical concepts, convert them into understandable drawings,
> and test decisions against real operations.

## Publication checklist

- Use no more than six notebook images in the public gallery.
- Rotate and crop each image for readability without removing crossed-out text.
- Do not add invented dates to individual pages.
- Exclude the third-party branding on the original notebook cover.
- Keep the Spanish handwriting visible and place the English translation in the
  caption or adjacent evidence document.
- Recheck every selected image for patient names, contact details, credentials,
  tokens, and Google Workspace data before publishing.
