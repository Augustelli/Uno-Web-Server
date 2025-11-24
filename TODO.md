# Mejoras al código


## Funcionamiento

* Modelos de datos
* Lógica del juego
* Manejo de errores
* Validación de entradas

## Seguridad 

* Actualmente **sin autenticación** ni **cifrado** (entorno controlado/educativo).
* Para exposición pública:

  * TLS.
  * Tokens de sesión / autenticación básica.
  * Límites de tamaño y rate-limit por conexión.


## Almacenamientos

* Almacenar fuera del servidor el estado de las partidas (Memcached, Redis, base de datos).
* Mejorar el modelo de datos.


## Logging

* Logs más detallados (acciones de jugadores, errores específicos).
* Integración con sistemas de monitoreo (Prometheus, Grafana).

## UX

* Crear GUI que adopte las funcionalidades del cliente.

## Escalabilidad

* Usar websocket para comunicación más eficiente con el cliente web.
* Migrar la aplicación a "stateless" usando bases de datos para el estado del juego y poder escalar horizontalmente.
* Mover hacia arquitecturas basadas en microservicios.
