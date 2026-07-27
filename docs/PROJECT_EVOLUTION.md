# From Experiments to Production

This document describes the preserved milestones behind Doko. It is not a
claim that every intermediate version was saved or that version numbers form a
complete source-control history.

## Mi contexto

Entré a 2026 después de perder mi trabajo en un hospital y atravesar una etapa
de inestabilidad personal y económica. Tenía experiencia práctica en compras
hospitalarias, almacén, proveedores y flujos de consultorio, pero no formación
formal como ingeniero de software.

En febrero empecé a usar herramientas de IA para aprender cómo convertir esa
experiencia en un servicio funcional. Mi objetivo no era presentar una demo
desechable ni afirmar conocimientos que no tenía. Quería construir un negocio
estable, recuperar un camino y crear un mejor futuro para mi familia.

Las herramientas de IA me explicaron conceptos que no conocía y me ayudaron a
implementar el producto. Yo aporté los problemas operativos, la observación en
consultorios, las decisiones de producto, los límites de seguridad, las
pruebas, el soporte a clientes y la responsabilidad por el servicio final.

## Before the program period

| Period | Preserved evidence | Classification | What it means |
| --- | --- | --- | --- |
| February-March 2026 | Earlier GitHub experiments and a March archive | Pre-existing learning | Broad agent and medical-software experiments were attempted and abandoned. They are not the submitted Doko product. |
| April 2026 | Configuración independiente de la página de reserva de Google Calendar y evidencia privada de pago | Relación previa con un cliente | Configuré para una doctora la página de reserva completa: disponibilidad, horarios, duración, ventana de reserva y reglas de agenda. Ese trabajo me permitió observar un flujo real de consultorio. El pago previo queda fuera del P&L del hackathon. |

The abandoned March archive contains obsolete credentials and service-account
material. It must never be committed or used as public evidence.

Antes de Doko también hablé con un amigo que trabaja por su cuenta en la venta
de insumos mediante su actividad independiente, Grupo Pangea. No era una
empresa grande ni un equipo de Doko. Consideramos ayudarnos mutuamente en el
futuro, pero esa conversación nunca se convirtió en una sociedad, relación con
un cliente, integración de proveedor, equipo de trabajo ni función de Doko.
No utilicé código, inventario, cartera de clientes, operación ni ingresos de
Grupo Pangea en el proyecto presentado.

## Preserved hackathon milestones

The official program period began on May 19, 2026.

| Date | Preserved artifact | What it demonstrates |
| --- | --- | --- |
| May 21-22 | `Untitled-2026-05-21-1050.excalidraw` | Earliest preserved integrated scene connecting login, OAuth, doctors, appointment radar, catalog, and orders. |
| May 27 | `01_especificaciones_tecnicas.md`, `03_cursorrules.md`, and related v4 planning | A formal Flask, PostgreSQL, Cloud Run, Calendar, Gmail, role, portal, and Suffy architecture. |
| May 29 | Devpost welcome email | Me registré en Devpost después de comenzar el diseño, todavía dentro del periodo oficial. |
| May 31 | `KB-TECH_Arquitectura_7_0.docx` | A more structured technical architecture milestone. |
| June 3 | `doko v8.1.zip`, `planificacion_tecnica_v9_0.md`, and `prompts_construccion_v9.md` | Transition from broad planning toward a controlled integrated build. |
| June 4 | `planificacion_tecnica_v9_1.md` and `prompts_construccion_v9_1.md` | Human approval, deterministic risk rules, safer persistence, and clearer service boundaries. |
| June 10 | `Rediseno Doko v9.2.pdf` | A mobile-first visual redesign before direct clinic use reshaped the product priorities. |
| June 19 onward | Founder field notes, clinic feedback, current repository, and production behavior | Direct clinic observation converted abstract modules into appointment, confirmation, search, portal, training, and operating workflows used by real doctors and assistants. |
| July 15 | `docs/evidence/load-test-2026-07-15.md` | Read-only concurrency validation of the panel assistant with deterministic fallbacks. |

I saved three June Excalidraw files named `dibujo +`, `dibujo v1`, and `dibujo`
separately because I initially thought each one preserved a different part of
the design. When I reviewed them, I confirmed that they are byte-identical
copies of the same scene, not three separate versions. I therefore treat them
as one preserved design artifact.

## Decisions that changed the product

### Reduce unnecessary clinical-data scope

Early experiments considered medical files, laboratory results, and broader
clinical agents. Doko removed those functions from the submitted product. The
current platform focuses on operations and does not present AI as medical
judgment.

### Keep deterministic rules in authority

Appointment state, permissions, confirmation timing, incident severity, and
operational writes are decided by application rules. Gemini may explain,
classify a redacted allowed intent, or draft a bounded analysis, but it cannot
override those rules.

### Use Google as an integrated scheduling layer

Google Calendar sigue siendo el componente de agenda confiable. Doko agrega el
panel adaptado al consultorio, el portal del paciente, la búsqueda de citas,
el ciclo de confirmación, la auditoría, la orientación operativa y la
visibilidad de fallas alrededor de esa agenda.

### Learn from the assistant's actual work

Direct observation showed that software alone was not enough. Doko added
temporary holds, blocks, manual confirmation, released-slot handling,
conversational read-only search, cancellation from the medical panel, and
versioned implementation protocols based on real front-desk work.

### Construir una plataforma adaptable, no una plantilla fija por especialidad

La dirección del producto cambió después de observar que cada especialidad y
cada consultorio trabajan de manera distinta. Doko conserva un núcleo
operativo común, pero activa capacidades específicas solo cuando un
consultorio real las necesita y las valida. Así Doko puede aprender y mejorar
con los consultorios, en lugar de copiar un flujo fijo para todos los médicos.

## Mi siguiente etapa

Quiero que Doko deje de ser visto solamente como una agenda. Mi objetivo es
que ayude a cada consultorio a tener más control del día a día: citas,
confirmaciones, cancelaciones, comunicación, presencia digital, capacitación y
procesos que puedan repetirse sin depender de la memoria de una sola persona.

Voy a buscar médicos de distintas especialidades para conocer sus flujos
reales. La idea es contar con médicos fundadores por especialidad y aprender
qué partes deben ser comunes y cuáles deben permanecer opcionales. Una
capacidad útil para ginecología no tiene por qué imponerse a cardiología, y
una herramienta que no sea necesaria debe poder permanecer desactivada.

También quiero que Doko ayude a convertir los aprendizajes aprobados por cada
consultorio en protocolos y capacitación. Doko no sustituye la responsabilidad
médica ni garantiza por sí solo el cumplimiento de normas; organiza el trabajo
y orienta el proceso para que el consultorio pueda operar con mayor claridad.

Doko Suffy continuará como una línea independiente para insumos médicos,
proveedores, inventario y entrega. Doko.lat puede apoyar la presencia digital,
pero no prometo que una página genere pacientes automáticamente. La visión es
construir una relación de confianza: que un médico asocie Doko con control,
tiempo y mejora continua, y que un paciente lo relacione con consultorios que
se esfuerzan por atender y organizar mejor su servicio.

### Narrow Suffy to a credible B2B operation

Early notes considered a broad range of services. The current Suffy scope is a
controlled B2B catalog, ordering, inventory, warehouse, supplier, and delivery
workflow. Potential partnerships and future procurement revenue are not
presented as current traction.

## What the evidence proves

- Dated digital artifacts establish preserved milestones inside the program
  period.
- The pocket notebook documents questions, learning, discarded ideas, and
  product reasoning; it is undated and is not used alone to establish dates.
- The current repository demonstrates the submitted implementation.
- The live service, sanitized logs, aggregate usage, payment evidence, and
  permissioned testimonials demonstrate operation and traction.

## What the evidence does not claim

- That every version between v1 and v9 was preserved.
- That Doko generated every appointment managed by the platform.
- That the current dashboard counts represent new patients generated by Doko.
- That abandoned pre-program experiments are part of the submitted code.
- That Grupo Pangea is a current partner, team member, customer, supplier
  integration, or source of Doko revenue.
- That future Suffy, directory, or procurement revenue has already been earned.
- That AI replaces medical or operational accountability.

## How the submission evidence is organized

### Public repository and project page

- Current source code and technical documentation.
- This project-evolution record.
- Six selected notebook pages with Spanish transcription and English context.
- Sanitized architecture, testing, AI-operation, and production-evidence
  summaries.
- Public product links and a demonstration made with test data.

### Judges and organizers only

- Cash-basis P&L and supporting receipts.
- Payment evidence and customer classification.
- Permissioned testimonials or public testimonial links.
- Any private operational proof needed to validate aggregate traction.

### Excluded completely

- Credentials, tokens, service-account files, and patient information.
- The obsolete February-March source archive.
- The unimplemented Grupo Pangea proposal and any of its independent business
  resources.
- Undated notebook pages that do not add clear evidence.
- Unverified future revenue, partnerships, or product capabilities.

## Core narrative

> Construí Doko durante el hackathon con aprendizaje y desarrollo apoyados por
> IA. El proyecto nació de mi experiencia operativa, de una configuración
> independiente de la página de reserva de Google Calendar y de la observación
> directa en consultorios. Esos aprendizajes se convirtieron en una plataforma
> de producción que ayuda a médicos y asistentes a controlar citas,
> confirmaciones, presencia digital, suministros y procesos repetibles, con
> límites deterministas y una IA de autoridad controlada.
