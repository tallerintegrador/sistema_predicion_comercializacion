**Índice:**

[**1\. Introducción 2**](#_9s2h5ju9jccf)

[**2\. Requisitos previos 2**](#_nrtzid2asvb5)

[2.1. Creación de la cuenta de docker hub 4](#_vjj5eu57gv7p)

[A. Entramos a dockerhub.com 4](#_x9hmimdx8ii)

[B. Creación de la cuenta 4](#_mmnhq7qq4i6d)

[C. Iniciando sesión con la cuenta creada anteriormente 5](#_yycuchi4d8rd)

[2.2. Creación de la cuenta de Render 7](#_rdghn3yjbckx)

[A. Ingresamos a render.com 7](#_hj478zqd7io5)

[B. Nos registramos 7](#_yh4kmtehlivs)

[C. Iniciamos sesión con la cuenta creada 9](#_a0wkxn8dlke2)

[2.3. Creación de la cuenta en Neon DB 10](#_jjgdvowr8e15)

[A. Ingresamos a neon.com 10](#_6668seov89r2)

[B. Registrarse en Neon 11](#_q18m4qxfp6y2)

[C. Verificar cuenta de Neon mediante correo 11](#_czcradr6wlms)

[D. Creación del proyecto 12](#_rj8pehce05xf)

[2.4. Obtener la cadena de conexión 15](#_zedew0yb6w3e)

[2.5. Creación de la cuenta de firebase 17](#_mk2l0w3i9riy)

[A. Accediendo a firebase.com 17](#_5f0tlzstxwve)

[B. Iniciando sesión con una cuenta de google 17](#_hy5cyhuvnyhv)

[2.6. Creación del proyecto en firebase 18](#_zhhfejbyikt5)

[**3\. Arquitectura general del despliegue 22**](#_oivgtiei0fv4)

[**4\. Variables de entorno 23**](#_cky2i1rql4hp)

[**5\. Despliegue del backend 24**](#_gpp0d4der3pk)

[5.1. Compilación del backend 24](#_py499lc3uyr1)

[5.2. Creación del Dockerfile 24](#_3nki3gelbg2t)

[5.3. Construcción de la imagen Docker 26](#_96cs53lwbyvk)

[5.4. Prueba local del contenedor 26](#_bnxnrqpjkju4)

[5.5. Publicación en Docker Hub 27](#_pg704ywad04n)

[5.6. Despliegue en Render 28](#_sbroweenf6il)

[Creamos un nuevo servicio 28](#_kgb23eprq1b2)

[Elegimos la fuente de lo que queremos desplegar 29](#_2929blrr5b1)

[**6\. Despliegue del frontend 32**](#_ijr82hwq4bmw)

[6.1. Instalación de dependencias 32](#_23bdeibbex2y)

[6.2. Configuración del endpoint del backend 32](#_2ubcyfqn2ame)

[6.3. Compilación del proyecto Angular 33](#_k6nfig6wrv7h)

[6.4. Configuración de Firebase Hosting 33](#_edjffggv0a7w)

[6.5. Publicación en Firebase 35](#_ejg29pbytsws)

[**7\. Configuración de CORS 36**](#_w9t3z7623eym)

[**8\. Verificación del despliegue 38**](#_kg1ytptoozsc)

[**9\. Mantenimiento y actualización 40**](#_gvr4zdy9zg16)

[**10\. Posibles errores y soluciones 41**](#_grw65k61w1xs)

[**11\. Seguridad del despliegue 42**](#_7v7l0zub20sk)

[**12\. Evidencias del despliegue 44**](#_5fq3059hzxfp)

[12.1. Evidencia del Dockerfile del backend 44](#_sj5xz19ffgkd)

[12.2. Evidencia de imagen publicada en Docker Hub 44](#_a0lywj2dh7ia)

[12.3. Evidencia del servicio backend en Render 45](#_ffr8d9n8mpgv)

[12.4. Evidencia de variables de entorno en Render 45](#_868ysge63bo)

[12.5. Evidencia de logs del backend 46](#_bbwfd36tyo9y)

[12.6. Evidencia del endpoint de salud 46](#_d0lvu81roywv)

[12.7. Evidencia del build del frontend 47](#_9fpocfuhv369)

[12.8. Evidencia de configuración de Firebase Hosting 47](#_4kwz8vu0z3v6)

[12.9. Evidencia del deploy en Firebase 47](#_egzrerx5xvuy)

[12.10. Evidencia de la aplicación publicada 48](#_hcu82sjsgewo)

[12.11. Evidencia del inicio de sesión 48](#_quhq5dp5ixno)

[**Conclusión 49**](#_bvmymvvo8f7z)

#

# **Introducción**

El presente manual describe el procedimiento necesario para desplegar el sistema web del comedor, compuesto por un backend desarrollado en Java Spring Boot bajo arquitectura hexagonal y un frontend desarrollado en Angular. El backend es construido mediante Docker, publicado en Docker Hub y desplegado en Render, mientras que el frontend es compilado en angular y publicado en Firebase Hosting.

# **Requisitos previos**

| **Componente**        | **Herramienta / Servicio** | **Versión o detalle**                    |
| --------------------- | -------------------------- | ---------------------------------------- |
| **Backend**           | Java Development Kit       | Java Development Kit (JDK)               |
| ---                   | ---                        | ---                                      |
| **Backend**           | Java                       | 21                                       |
| ---                   | ---                        | ---                                      |
| **Backend**           | Spring Boot                | Framework principal                      |
| ---                   | ---                        | ---                                      |
| **Backend**           | Spring Security            | Seguridad, autenticación y refresh token |
| ---                   | ---                        | ---                                      |
| **Backend**           | Docker                     | Para crear la imagen del backend         |
| ---                   | ---                        | ---                                      |
| **Backend**           | Maven                      | Gestor de dependencias y compilación     |
| ---                   | ---                        | ---                                      |
| **Backend**           | Docker Hub                 | Para almacenar la imagen Docker          |
| ---                   | ---                        | ---                                      |
| **Backend**           | Render                     | Para desplegar el servicio backend       |
| ---                   | ---                        | ---                                      |
| **Frontend**          | Angular CLI                | 21.2.8                                   |
| ---                   | ---                        | ---                                      |
| **Frontend**          | Node.js                    | 24.15.0                                  |
| ---                   | ---                        | ---                                      |
| **Frontend**          | npm                        | 11.12.1                                  |
| ---                   | ---                        | ---                                      |
| **Frontend**          | Firebase CLI               | Para publicar en Firebase Hosting        |
| ---                   | ---                        | ---                                      |
| **Sistema operativo** | Windows                    | win32 x64                                |
| ---                   | ---                        | ---                                      |

#

#

#

**Además, se requiere contar con:**

- Cuenta activa en Docker Hub.
- Cuenta activa en Render.
- Cuenta activa en Firebase.
- Proyecto creado en Firebase Hosting.
- Acceso al código fuente del backend y frontend.  
   <https://github.com/Gestion-de-inventario/Backend/tree/develop>
- Variables de entorno configuradas para producción.
- Conexión a la base de datos del sistema.

**A continuación daremos una breve guía para poder completar con los requisitos adicionales:**

## **Creación de la cuenta de docker hub**

### **Entramos a dockerhub.com**

Para poder crearnos la cuenta debemos de ingresar a :

<https://hub.docker.com>

**Figura 1. Landing page de dockerHub**


Le daremos en el boton de "Sign up" para crear nuestra cuenta.

### **Creación de la cuenta**

Podemos crear una cuenta con un correo electrónico o usando una cuenta de google o incluso una cuenta de github

**Figura 2. Formulario de creación de cuenta en dockerHub**


### **Iniciando sesión con la cuenta creada anteriormente**

Con nuestra cuenta ya creada y confirmada podremos proceder a iniciar sesión

**Figura 3. Formulario de inicio de sesión en dockerHub**


Podremos visualizar nuestro nombre de usuario el cual será importante a la hora de construir el contenedor y subirlo a docker hub

**Figura 4. Detalles de la cuenta creada**


## **Creación de la cuenta de Render**

### **Ingresamos a render.com**

Para crear nuestra cuenta de render debemos ingresar a :

<https://render.com>

**Figura 5. Landing page de Render**


Y seleccionamos en "Get Started" para registrarnos.

### **Nos registramos**

Podemos usar un correo electrónico o una de las otras formas que render nos ofrece.

**Figura 6. Formulario de creación de cuenta de Render**


Se nos enviará un correo para confirmar la cuenta :

**Figura 7 . Confirmación de creación de la cuenta en Render**


Correo recibido :

**Figura 8. Correo de confirmación de cuenta**


Le daremos en **"Verify your email"**

**Figura 9. Notificación de cuenta de Render confirmada**


**Se nos mostrará una encuesta :**

**Figura 10. Encuesta de bienvenida**



### **Iniciamos sesión con la cuenta creada**

Una vez creada y confirmada la cuenta podemos iniciar sesión

**Figura 11. Detalles de la cuenta creada en Render**


Con la cuenta ya creada podemos proseguir.

## **Creación de la cuenta en Neon DB**

### **Ingresamos a neon.com**

Una vez dentro le damos click en el botón de "SignUp" para crear una cuenta.

**Figura 12. Landing page de Neon.com**


### **Registrarse en Neon**

Nos registramos utilizando un correo electrónico o algún otro método ofrecido por Neon.

**Figura 13. Formulario de creación de cuenta de Neon**


### **Verificar cuenta de Neon mediante correo**

Se nos enviará una verificación al correo con el que nos registramos.

**Figura 14. Mensaje de aviso de verificación necesaria**


Una vez recibido el correo de verificación le daremos en "Active account"

**Figura 15. Correo de activación de cuenta en Neon**


Una vez activado se nos redirigirá a la creación del proyecto, pero lo detallaremos más en el siguiente punto.

### **Creación del proyecto**

Una vez creada la cuenta podemos iniciar sesión y seleccionar en crear un proyecto:

**Figura 16. Dashboard de la cuenta en Neon**


Si hemos iniciado sesión directamente la organización vendrá con un nombre por defecto, pero si hemos accedido desde el enlace de verificación se nos mostrará esta guía de inicialización:

**Figura 17. Configuración inicial de Neon**


Como se puede observar se nos permitirá incluso invitar a otros usuarios a nuestra organización.

**Figura 18. Creación del primer proyecto desde guía inicial**


**Figura 19. Creación del primer proyecto desde dashboard**


Si nos fijamos en ambas maneras de crear el primer proyecto es similar en ambas formas nos piden el nombre, la versión de postgre y la ubicación del servidor.

En este caso la versión de postgre será la 18 y la ubicación será lo más cercano a la ubicación de nuestro backend, Oregon

Una vez configurado le damos en "Create" (crear)

**Figura 20. Formulario de creación de proyecto completado.**


Una vez creado el proyecto procedemos a obtener la cadena de conexión , la cual nos servirá para conectar nuestro servidor de backend a la base de datos.

## **Obtener la cadena de conexión**

Una vez creado la cuenta, la organización y el proyecto nos mostrara algo asi el dashboard principal del proyecto:

**Figura 21. Dashboard del proyecto creado en Neon**


Ahora para conectarnos deberemos de clickear en el botón que dice "Connect"

**Figura 22. Botón para obtener la cadena de conexión de Neon**


Desactivamos el conection pooling, y mostramos la contraseña para facilitarnos la extracción de los valores necesarios :

**Figura 23. Desactivando el conection polling y mostrando la contraseña**


Bien una vez mostrada la cadena de conexión, vamos a extraer 3 valores importantes los cuales servirán para las variables de entorno :

DB_URL, DB_USER y DB_PASSWORD.

**Figura 24. Cadena de conexión**


lo que esta entre los primeros // y antes de los 2 puntos (:) viene a ser el usuario de base de datos, entonces para este caso de ejemplo :

DB_USER = neondb_owner

Para la contraseña sera lo que esta entre los 2 puntos (:) hasta el arroba "@", entonces quedando :

DB_PASSWORD: npg_bN5gC7WIRMef

Para la url de la base de datos, vamos a necesitar el valor de la cadena de conexión + unos valores ya establecidos,

jdbc:postgresql://**\[url de base de datos \]**:5432/**\[nombre de la base de datos\]**

Para este ejemplo entonces lo que esta despues del arroba "@" hasta antes del "/" :

jdbc:postgresql://ep-blue-band-a6wrdr69.us-west-2.aws.neon.tech:5432/neondb

_Nota: No probar esta cadena de conexión, ha sido eliminada , solo fue para ejemplificar_

## **Creación de la cuenta de firebase**

### **Accediendo a firebase.com**

Ingresamos a firebase.com y le damos a acceder, en esta ocasión solo podremos usar una cuenta de google.

**Figura 25. Landing de firebase.com**


### **Iniciando sesión con una cuenta de google**

Iniciamos sesión en nuestra cuenta de google

**Figura 26. Inicio de sesión con cuenta google**


Una vez iniciado sesión con google le damos click en "ir a la consola "

**Figura 27. Ir a la consola de firebase.com**


## **Creación del proyecto en firebase**

Una vez dentro de la consola le damos en crear un proyecto de Firebase

**Figura 28. Consola de firebase.com**


Ingresamos el nombre de nuestro proyecto , aceptamos los términos y creamos nuestro primer proyecto.

**Figura 29. Creación del proyecto en firebase**


Se nos preguntará si deseamos activar google analytics, en este caso le dire que no.

**Figura 30. Desactivando google analytics del proyecto**


Una vez creado el proyecto deberemos esperar unos segundos y se nos mostrará lo siguiente:

**Figura 31. Detalles del proyecto creado**


Lo siguiente vendría a ser la instalación de firebase cli

**_npm install -g firebase-tools_**

Para luego loguearse con fierebase login y empezar la configuración en la terminal con firebase init.

Se puede ver más detalles si entramos a la sección de "Hosting y sin servidores" y luego clickear "Hosting"

**Figura 32. Sección de Hosting en firebase**


Una vez dentro de la sección de hosting podremos darle en "empezar" para que google nos de una guía complementaria a la que verá más adelante acerca de cómo configurar firebase cli.

**Figura 33. Hosting firebase**


**Figura 34. Guía complementaria para configuración de firebase hosting**


# **Arquitectura general del despliegue**

El sistema se despliega utilizando una arquitectura separada entre frontend y backend.

| **Módulo**             | **Tecnología**                        | **Plataforma de despliegue** |
| ---------------------- | ------------------------------------- | ---------------------------- |
| **Frontend**           | Angular                               | Firebase Hosting             |
| ---                    | ---                                   | ---                          |
| **Backend**            | Java Spring Boot                      | Render                       |
| ---                    | ---                                   | ---                          |
| **Contenedor backend** | Docker                                | Docker Hub                   |
| ---                    | ---                                   | ---                          |
| **Seguridad**          | Spring Security + JWT + Refresh Token | Backend                      |
| ---                    | ---                                   | ---                          |
| **Base de datos**      | Postgre 18                            | Neon DB                      |
| ---                    | ---                                   | ---                          |

La comunicación general del sistema se realiza de la siguiente manera:

Usuario → Firebase Hosting → Angular → API REST → Render → Backend Spring Boot → Base de datos

El frontend Angular se publica como una Single-Page Application, también conocida como SPA. Esta aplicación consume los servicios REST expuestos por el backend desplegado en Render.

El backend se ejecuta como una aplicación Java Spring Boot dentro de un contenedor Docker. La imagen Docker se publica en Docker Hub con la siguiente referencia:

**javierabgzk/comedor:latest**

Posteriormente, Render utiliza dicha imagen para ejecutar el servicio backend.

# **Variables de entorno**

El backend requiere variables de entorno para conectarse con servicios externos, gestionar la autenticación y proteger información sensible.

**En Render se configuran las siguientes variables:**

| **Variable**       | **Descripción**                                                       |
| ------------------ | --------------------------------------------------------------------- |
| **DB_URL**         | URL de conexión a la base de datos                                    |
| ---                | ---                                                                   |
| **DB_USER**        | Usuario de la base de datos                                           |
| ---                | ---                                                                   |
| **DB_PASSWORD**    | Contraseña de la base de datos                                        |
| ---                | ---                                                                   |
| **JWT_SECRET**     | Clave secreta utilizada para la generación y validación de tokens JWT |
| ---                | ---                                                                   |
| **JWT_EXPIRATION** | Tiempo de expiración del token JWT                                    |
| ---                | ---                                                                   |
| **RENIEC_TOKEN**   | Token utilizado para consumir el servicio externo de RENIEC           |
| ---                | ---                                                                   |

Por seguridad, los valores reales de estas variables no deben colocarse directamente en el código fuente ni en el repositorio del proyecto. Estos valores deben configurarse desde el panel de Render, dentro del apartado de variables de entorno del servicio.

**Figura 35. Variables de entorno configuradas en Render**


# **Despliegue del backend**

El backend del sistema fue desarrollado con Java Spring Boot, aplicando arquitectura hexagonal para separar la lógica de negocio, los puertos de entrada y salida, y los adaptadores externos.

El despliegue del backend se realiza mediante Docker, Docker Hub y Render.

## **Compilación del backend**

El proyecto backend utiliza Maven como gestor de dependencias y herramienta de compilación.

Para compilar el proyecto y generar el archivo .jar, se ejecuta el siguiente comando desde la raíz del backend:

mvn clean package -DskipTests

Este comando realiza la limpieza del proyecto, descarga las dependencias necesarias y genera el archivo ejecutable dentro de la carpeta target.

El parámetro -DskipTests permite omitir temporalmente la ejecución de pruebas durante el empaquetado del proyecto, lo cual puede ser útil para acelerar el proceso de construcción de la imagen Docker.

## **Creación del Dockerfile**

El backend cuenta con un archivo Dockerfile que permite construir una imagen Docker de la aplicación.

El archivo utilizado es el siguiente:

FROM maven:3.9.6-eclipse-temurin-21 AS build

WORKDIR /app

COPY . .

RUN mvn clean package -DskipTests

FROM eclipse-temurin:21-jdk

WORKDIR /app

COPY --from=build /app/target/\*.jar app.jar

EXPOSE 8080

ENTRYPOINT \["java", "-jar", "app.jar"\]

**Este Dockerfile utiliza una construcción en dos etapas:**

| **Etapa**                 | **Descripción**                                                                      |
| ------------------------- | ------------------------------------------------------------------------------------ |
| **Etapa de construcción** | Usa Maven con Eclipse Temurin 21 para compilar el proyecto y generar el archivo .jar |
| ---                       | ---                                                                                  |
| **Etapa de ejecución**    | Usa Eclipse Temurin 21 JDK para ejecutar el archivo app.jar                          |
| ---                       | ---                                                                                  |

##

El backend expone el puerto 8080, el cual es utilizado por Spring Boot para recibir las solicitudes HTTP.

**Figura 36. Archivo Dockerfile del backend**


## **Construcción de la imagen Docker**

Antes de construir la imagen es importante eliminar la configuración de Env Config, debido a que causa conflicto, no es necesario realizar la lectura desde un archivo .env ya que se está configurando directamente en render las variables de entorno.

Para construir la imagen Docker del backend, se ejecuta el siguiente comando desde la raíz del proyecto backend:

**docker build -t comedor .**

Luego, se etiqueta la imagen con el nombre del repositorio de Docker Hub:

**docker tag comedor javierabgzk/comedor:latest**

Esta etiqueta permite identificar la imagen dentro de Docker Hub como la versión más reciente disponible para despliegue.

## Prueba local del contenedor

Antes de publicar la imagen en Docker Hub, se recomienda ejecutar el contenedor localmente para verificar que el backend inicia correctamente.

El comando de prueba local es el siguiente:

docker run -p 8080:8080 \`

\-e DB_URL="\*\*\*" \`

\-e DB_USER="\*\*\*" \`

\-e DB_PASSWORD="\*\*\*" \`

\-e JWT_SECRET="\*\*\*" \`

\-e JWT_EXPIRATION="\*\*\*" \`

\-e RENIEC_TOKEN="\*\*\*" \` javierabgzk/comedor

Luego se puede comprobar el funcionamiento del backend accediendo al endpoint de salud:

<http://localhost:8080/api/v1/health>

El backend cuenta con un endpoint de verificación implementado de la siguiente manera:

_@RestController_

_@RequestMapping("/health")_

_public class SecretController {_

_@GetMapping_

_public String health() {_

_return PeruTime.now() + " OK";_

_}_

_}_

Este endpoint devuelve la hora actual del servidor y el texto OK, lo cual permite confirmar que el servicio se encuentra activo.

## Publicación en Docker Hub

Para publicar la imagen en Docker Hub, primero se inicia sesión desde la terminal:

docker login

Luego se sube la imagen previamente etiquetada:

docker push javierabgzk/comedor:latest

Una vez publicada, la imagen queda disponible en Docker Hub con la siguiente referencia:

javierabgzk/comedor:latest

**Figura 37. Imagen del backend publicada en Docker Hub**


## **Despliegue en Render**

El despliegue del backend se realiza en Render utilizando la imagen publicada en Docker Hub.

**El proceso aplicado es el siguiente:**

- Ingresar a la cuenta de Render.
- Crear o seleccionar el servicio web correspondiente al backend.
- Configurar el servicio para utilizar una imagen Docker externa.
- Indicar la imagen publicada en Docker Hub: **_javierabgzk/comedor:latest_**
- Configurar las variables de entorno necesarias:

- DB_URL
- DB_USER
- DB_PASSWORD
- JWT_SECRET
- JWT_EXPIRATION
- RENIEC_TOKEN

- Ejecutar el despliegue manualmente desde Render.
- Verificar que el servicio se encuentre activo.

El backend desplegado en Render se encuentra disponible en la siguiente URL base:

**_<https://comedor-latest.onrender.com/api/v1/>_**

El endpoint de verificación del backend desplegado es:

**_<https://comedor-latest.onrender.com/api/v1/health>_**

El despliegue desde Docker Hub no se ejecuta automáticamente. Cada vez que se publica una nueva versión de la imagen Docker, se debe realizar el redeploy manual desde Render.

Sí es la primera vez que se despliega, se deberá configurar la fuente del contenedor.

### **Creamos un nuevo servicio**

Si no hemos creado un espacio de trabajo desde la guia que se nos mostrará al confirmar el correo el nombre de nuestro espacio de trabajo será el por defecto, esto puede cambiarse más adelante en la sección de configuración.

Independientemente si se ha configurado un nombre o no para el espacio de trabajo, podemos crear un servicio, para esta ocasión crearemos un servicio de tipo **WEB SERVICES**

**Figura 38. Panel inicial de Render**


### **Elegimos la fuente de lo que queremos desplegar**

Una vez creado deberemos de elegir la fuente de donde se va a obtener el código fuente, en nuestro caso lo obtendremos de docker hub.

**Figura 39. Elección de fuente de código**


Elegimos la opción **"Existing Image"**

**Figura 40. Fuente Existing image**


Introducimos el enlace a nuestra imagen subida en docker hub

nota: Se usó un contenedor de ejemplo

**Figura 41. Uso de la imagen subida a dockerHub**


Clickeamos en conectar :

**Figura 42. Completar la configuración dando click en conectar**


**Elegimos el plan y la ubicación de despliegue :**

**Figura 43. Sección del plan de despliegue y la ubicación del servidor**


Confirmamos que las variables de entorno estén configuradas:


Y finalmente le damos en "Deploy Web Service"

**Figura 45. Servicio backend activo en Render**


**Figura 46. Endpoint de salud del backend ejecutándose correctamente**


# **Despliegue del frontend**

El frontend del sistema fue desarrollado con Angular y se despliega mediante Firebase Hosting.

La aplicación Angular está configurada como una Single-Page Application, por lo que Firebase debe redirigir todas las rutas internas hacia index.html.

## **Instalación de dependencias**

Desde la raíz del proyecto frontend, se instalan las dependencias con el siguiente comando:

**npm install**

Las versiones utilizadas en el entorno de desarrollo son:

| **Herramienta**       | **Versión** |
| --------------------- | ----------- |
| **Angular CLI**       | 21.2.2008   |
| ---                   | ---         |
| **Node.js**           | 24.15.0     |
| ---                   | ---         |
| **npm**               | 11.12.2001  |
| ---                   | ---         |
| **Sistema operativo** | win32 x64   |
| ---                   | ---         |

##

## Configuración del endpoint del backend

El frontend consume el backend mediante archivos de entorno ubicados en la carpeta environments.

La estructura utilizada es la siguiente:

environments/

├── environment.prod.ts

└── environment.ts

Para desarrollo local, el archivo environment.ts apunta al backend local:

export const environment = {

production: false, apiUrl: '<http://localhost:8080/api/v1>',

};

Para producción, el archivo environment.prod.ts apunta al backend desplegado en Render:

export const environment = {

production: true, apiUrl: '<https://comedor-latest.onrender.com/api/v1>',

};

Esta configuración permite que, durante el desarrollo, Angular consuma el backend local, mientras que en producción utiliza la API publicada en Render.

## **Compilación del proyecto Angular**

El nombre del proyecto Angular configurado en angular.json es:

comedor-frontend

Para compilar el frontend en modo producción, se ejecuta el siguiente comando:

**ng build --configuration production**

También se puede utilizar el script equivalente si se encuentra configurado en package.json:

**npm run build**

La carpeta generada para producción es:

**dist/comedor-frontend/browser**

Esta carpeta contiene los archivos estáticos que serán publicados en Firebase Hosting.

**Figura 47. Compilación exitosa del proyecto Angular**


## **Configuración de Firebase Hosting**

El proyecto utiliza Firebase Hosting para publicar el frontend.

El archivo firebase.json se encuentra configurado de la siguiente manera:

{ "hosting": {

"public": "dist/comedor-frontend/browser",

"ignore": \[

"firebase.json",

"\*\*/.\*",

"\*\*/node_modules/\*\*"

\],

"rewrites": \[

{

"source": "\*\*",

"destination": "/index.html"

} \] }}

La propiedad public indica la carpeta que Firebase debe publicar.

La sección rewrites permite que todas las rutas internas de Angular redirijan hacia index.html. Esta configuración es necesaria porque el frontend funciona como una Single-Page Application.

**Algunas rutas internas utilizadas por la aplicación son:**

| **Ruta**                      | **Descripción**             |
| ----------------------------- | --------------------------- |
| **/login**                    | Inicio de sesión            |
| ---                           | ---                         |
| **/dashboard**                | Panel principal             |
| ---                           | ---                         |
| **/management/users**         | Gestión de usuarios         |
| ---                           | ---                         |
| **/management/beneficiaries** | Gestión de beneficiarios    |
| ---                           | ---                         |
| **/roles**                    | Gestión de roles y permisos |
| ---                           | ---                         |
| **/profile**                  | Perfil del usuario          |
| ---                           | ---                         |
| **/menu-report**              | Orden de producción         |
| ---                           | ---                         |
| **/beneficiaries-control**    | Orden de salida             |
| ---                           | ---                         |
| **/purchase-order**           | Órdenes de entrada          |
| ---                           | ---                         |
| **/inventory/products**       | Gestión de productos        |
| ---                           | ---                         |
| **/inventory/dishes**         | Gestión de platos o menús   |
| ---                           | ---                         |
| **/inventory/categories**     | Gestión de categorías       |
| ---                           | ---                         |
| **/inventory/tags**           | Gestión de etiquetas        |
| ---                           | ---                         |
| **/reports**                  | Reportes del sistema        |
| ---                           | ---                         |

##

##

Gracias al rewrite hacia index.html, al recargar cualquiera de estas rutas en el navegador, Firebase no devuelve error 404.

**Figura 48. Archivo firebase.json configurado para SPA**


## Publicación en Firebase

Para publicar el frontend en Firebase Hosting, primero se debe iniciar sesión en Firebase CLI:

**firebase login**

Luego, desde la raíz del proyecto frontend, se ejecuta el despliegue:

**firebase deploy**

Al finalizar el proceso, Firebase publica la aplicación en la siguiente URL:

**<https://comedorpopularluzdeisrael.web.app/>**

**Figura 49. Despliegue exitoso en Firebase Hosting**


**Figura 50. Aplicación frontend funcionando en Firebase Hosting**


# **Configuración de CORS**

Debido a que el frontend y el backend se encuentran desplegados en dominios diferentes, es necesario configurar CORS en el backend.

El frontend se encuentra alojado en Firebase Hosting:

**<https://comedorpopularluzdeisrael.web.app>**

Mientras que el backend se encuentra alojado en Render:

**<https://comedor-latest.onrender.com/api/v1/>**

Para permitir la comunicación entre ambos servicios, se configuró CORS en Spring Boot de la siguiente manera:

@Configuration

public class CorsConfig {

@Bean

public CorsConfigurationSource corsConfigurationSource() {

CorsConfiguration config = new CorsConfiguration();

config.setAllowedOrigins(List.of("<http://localhost:4200","https://comedorpopularluzdeisrael.web.app>"));

config.setAllowedMethods(List.of("GET","POST","PUT","DELETE","PATCH","OPTIONS"));

config.setAllowedHeaders(List.of("\*"));

config.setAllowCredentials(true);

UrlBasedCorsConfigurationSource source =

new UrlBasedCorsConfigurationSource();

source.registerCorsConfiguration("/\*\*", config);

return source;

}

}

Esta configuración permite solicitudes desde el entorno local de Angular y desde el dominio público de Firebase Hosting.

Además, se habilita setAllowCredentials(true) porque el sistema utiliza refresh token mediante cookie HttpOnly. Esta configuración permite que el navegador envíe credenciales en las solicitudes autorizadas.

**Figura 51. Configuración CORS del backend**


# **Verificación del despliegue**

Luego de realizar el despliegue, se deben ejecutar verificaciones para confirmar que el sistema funciona correctamente.

| **N.º** | **Verificación**                                  | **Resultado esperado**                                                |
| ------- | ------------------------------------------------- | --------------------------------------------------------------------- |
| **1**   | Acceder a la URL del frontend en Firebase         | La aplicación carga correctamente                                     |
| ---     | ---                                               | ---                                                                   |
| **2**   | Recargar una ruta interna, por ejemplo /dashboard | La aplicación no muestra error 404                                    |
| ---     | ---                                               | ---                                                                   |
| **3**   | Acceder al endpoint /api/v1/health del backend    | El backend responde con fecha/hora y OK                               |
| ---     | ---                                               | ---                                                                   |
| **4**   | Iniciar sesión desde el frontend                  | El usuario accede correctamente al sistema                            |
| ---     | ---                                               | ---                                                                   |
| **5**   | Validar consumo de API REST desde Angular         | El frontend recibe datos desde Render                                 |
| ---     | ---                                               | ---                                                                   |
| **6**   | Revisar consola del navegador                     | No se presentan errores de CORS                                       |
| ---     | ---                                               | ---                                                                   |
| **7**   | Revisar logs en Render                            | El backend no presenta errores críticos                               |
| ---     | ---                                               | ---                                                                   |
| **8**   | Verificar conexión con base de datos              | Los datos se registran y consultan correctamente                      |
| ---     | ---                                               | ---                                                                   |
| **9**   | Validar refresh token                             | La sesión puede renovarse mediante cookie HttpOnly                    |
| ---     | ---                                               | ---                                                                   |
| **10**  | Probar módulos principales                        | Inventario, beneficiarios, órdenes y reportes funcionan correctamente |
| ---     | ---                                               | ---                                                                   |

**Figura 52. Verificación del endpoint de salud**


**Figura 53. Inicio de sesión exitoso desde Firebase Hosting**


# Mantenimiento y actualización

Cuando se realicen cambios en el backend, se debe generar una nueva imagen Docker, publicarla en Docker Hub y ejecutar el redeploy manual en Render.

**Actualización del backend:**

**Desde la raíz del backend:**

**_mvn clean package -DskipTests_**

Construcción de la imagen:

**_docker build -t comedor ._**

Etiquetado de la imagen:

**_docker tag comedor javierabgzk/comedor:latest_**

Publicación en Docker Hub:

**_docker push javierabgzk/comedor:latest_**

Finalmente, en Render se debe ejecutar manualmente el redeploy del servicio para que tome la imagen más reciente.

**Figura 54. Redeploy manual del backend en Render**


**Actualización del frontend**

Cuando se realicen cambios en el frontend, se debe compilar nuevamente el proyecto Angular y publicar la nueva versión en Firebase Hosting.

**Desde la raíz del frontend:**

**_npm install_**

Compilación de producción:

**_ng build --configuration production_**

Publicación en Firebase:

**_firebase deploy_**

Al finalizar, Firebase Hosting actualizará la aplicación publicada en:

**_<https://comedorpopularluzdeisrael.web.app/>_**

# **Posibles errores y soluciones**

| **Error**                                      | **Posible causa**                                      | **Solución**                                                        |
| ---------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------- |
| **Error de CORS**                              | El backend no permite el dominio del frontend          | Agregar el dominio de Firebase en la configuración CORS             |
| ---                                            | ---                                                    | ---                                                                 |
| **Error 404 al recargar rutas internas**       | Firebase no está configurado como SPA                  | Configurar rewrite hacia /index.html en firebase.json               |
| ---                                            | ---                                                    | ---                                                                 |
| **Backend no inicia en Render**                | Variables de entorno incompletas o incorrectas         | Revisar DB_URL, DB_USER, DB_PASSWORD, JWT_SECRET y demás variables  |
| ---                                            | ---                                                    | ---                                                                 |
| **La imagen Docker no se actualiza en Render** | El despliegue no es automático                         | Ejecutar redeploy manual en Render                                  |
| ---                                            | ---                                                    | ---                                                                 |
| **Frontend consume localhost**                 | Archivo de entorno de producción mal configurado       | Verificar environment.prod.ts                                       |
| ---                                            | ---                                                    | ---                                                                 |
| **Error de conexión a base de datos**          | Credenciales o URL incorrectas                         | Validar la configuración de la base de datos en Render              |
| ---                                            | ---                                                    | ---                                                                 |
| **Error al enviar refresh token**              | Configuración incorrecta de cookies o credenciales     | Verificar CORS, allowCredentials y configuración de cookie HttpOnly |
| ---                                            | ---                                                    | ---                                                                 |
| **Error en firebase deploy**                   | Firebase CLI no autenticado o proyecto mal configurado | Ejecutar firebase login y revisar firebase.json                     |
| ---                                            | ---                                                    | ---                                                                 |
| **Error de límite de tamaño en Angular**       | Presupuesto de build excedido                          | Revisar dependencias, optimización y configuración de budgets       |
| ---                                            | ---                                                    | ---                                                                 |
| **Endpoint /health no responde**               | Backend detenido o URL incorrecta                      | Revisar logs en Render y validar la URL /api/v1/health              |
| ---                                            | ---                                                    | ---                                                                 |

#

#

# **Seguridad del despliegue**

El sistema aplica medidas básicas de seguridad durante el despliegue y la ejecución en producción.

En el backend se utiliza Spring Security para proteger los endpoints y gestionar la autenticación. El sistema trabaja con access token y refresh token.

El access token se mantiene en memoria en el frontend, por lo que al recargar la página se elimina. Esto reduce el riesgo de exposición frente a ataques XSS, ya que no se almacena en localStorage.

El refresh token se maneja mediante una cookie HttpOnly. Esta estrategia impide que JavaScript acceda directamente al refresh token, reduciendo el riesgo de robo mediante inyección de scripts.

**Las principales consideraciones de seguridad son:**

- No almacenar tokens sensibles en localStorage.
- Usar refresh token en cookie HttpOnly.
- Configurar CORS solo para dominios permitidos.
- No publicar contraseñas ni secretos en el repositorio.
- Usar variables de entorno para datos sensibles.
- Mantener el backend y frontend bajo HTTPS.
- No exponer valores reales de JWT_SECRET, DB_PASSWORD o RENIEC_TOKEN.
- Revisar los logs de Render después de cada despliegue.
- Mantener actualizadas las dependencias del proyecto.

**Figura 55. Configuración de seguridad del backend**


# \*\*Evidencias del despliegue

\*\*

## **Evidencia del Dockerfile del backend**


## **Evidencia de imagen publicada en Docker Hub**


## **Evidencia del servicio backend en Render**


## **Evidencia de variables de entorno en Render**


## **Evidencia de logs del backend**


## **Evidencia del endpoint de salud**


## **Evidencia del build del frontend**


## **Evidencia de configuración de Firebase Hosting**


## **Evidencia del deploy en Firebase**


## **Evidencia de la aplicación publicada**


## **Evidencia del inicio de sesión**


# **Conclusión**

El despliegue del sistema se realizó separando el frontend y el backend en plataformas especializadas. El frontend Angular fue publicado mediante Firebase Hosting, mientras que el backend Spring Boot fue containerizado con Docker, publicado en Docker Hub y ejecutado en Render.

Esta estrategia permite mantener una arquitectura de despliegue ordenada, donde el frontend consume una API REST pública y el backend concentra la lógica de negocio, seguridad, conexión con base de datos y servicios externos.

Asimismo, el uso de variables de entorno, Spring Security, access token en memoria, refresh token mediante cookie HttpOnly y configuración CORS permite reforzar la seguridad del sistema durante su ejecución en producción.