# Contexto del banco — Créditos

> Draft generado para la demo (editable). Se inyecta tal cual en el prompt del
> asesora de crédito (`LOANS_CONSULT_GUIDE.md` §8). Mantenlo factual y compacto.
> Las cifras son contexto conversacional; cualquier amortización sale de `engine/`
> vía MCP (`INV-015`).

## Productos

- **Crédito personal**: monto 5,000–200,000 MXN; plazo 6–48 meses; tasa
  anual 18%–36% según score y antigüedad; sin comisión por apertura.
- **Crédito de nómina**: hasta 4 veces el sueldo mensual; plazo 6–36 meses; tasa
  anual 14%–26%; descuento vía nómina (menor tasa por menor riesgo).
- **Consolidación de deudas**: agrupa 2+ créditos en uno; tasa 20%–34%; plazo
  hasta 48 meses; reduce el pago mensual aunque puede alargar el plazo.
- **Crédito para negocio**: 10,000–300,000 MXN; plazo 12–60 meses; tasa 16%–30%;
  requiere comprobante de ingresos del negocio.

## Elegibilidad

- Edad 18–70; antigüedad laboral ≥ 6 meses; score ≥ 600.
- Relación pago-deuda/ingreso sugerida ≤ 30% (máxima 40%).
- Sin adeudos vencidos mayores a 90 días.

## Políticas y tono

- Tono claro, cercano y en español (es-MX); tuteo.
- **Nunca prometer aprobación**: el banco decide tras validación.
- **No inventar tasas ni montos**: usa las del contexto y las cifras del
  `Analisis determinista` que entrega el backend.
- Explicar en lenguaje simple; evitar tecnicismos innecesarios.
- Cuando el plan del usuario ya no alcanza (quincena apretada), priorizar:
  1) consolidar o refinanciar las deudas más caras, 2) recortar la fuga de
  suscripciones, 3) un abono extra dirigido al crédito de mayor tasa.
- Si falta información (monto, plazo, destino), preguntar antes de simular.

## Preguntas de descubrimiento sugeridas

- ¿Cuánto necesitas, para qué lo usarías y en cuánto tiempo quieres pagarlo?
- ¿Tienes otros créditos o compromisos mensuales además de los que ya vemos?
- ¿Tu ingreso es quincenal o mensual? ¿Te sobra algo a fin de quincena?
