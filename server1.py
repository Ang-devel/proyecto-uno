import os
import re
import math
import uuid
from datetime import date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]

# Configuración de la cookie de sesión (necesaria para que se guarde bien en local)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # ponlo en True solo cuando uses HTTPS


def supabase_client():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"]
    )


def supabase_admin():
    """Cliente con permiso para ESCRIBIR en la base de datos (solo se usa en el servidor)."""
    clave = os.environ.get("SUPABASE_SERVICE_KEY")
    if not clave:
        raise RuntimeError("Falta SUPABASE_SERVICE_KEY en el archivo .env")
    return create_client(os.environ["SUPABASE_URL"], clave)


def explicar_error_guardado(e):
    """Convierte el error de Supabase en un mensaje claro para mostrar en pantalla."""
    texto = str(getattr(e, "message", "") or e)
    bajo = texto.lower()
    if isinstance(e, RuntimeError):
        return "Falta configurar la clave de escritura: agrega SUPABASE_SERVICE_KEY en el archivo .env y reinicia Flask."
    if "imagen" in bajo and ("column" in bajo or "pgrst204" in bajo):
        return "La tabla libros no tiene la columna 'imagen'. En Supabase (SQL Editor) ejecuta: alter table public.libros add column if not exists imagen text;"
    if "prestamos" in bajo and ("does not exist" in bajo or "could not find" in bajo or "pgrst205" in bajo or "42p01" in bajo):
        return "Falta crear la tabla 'prestamos' en Supabase. Ejecuta el SQL de la tabla prestamos en el SQL Editor."
    if "row-level security" in bajo or "42501" in bajo:
        return "Supabase rechazó el guardado por permisos. Revisa que SUPABASE_SERVICE_KEY sea la clave service_role (secret) y no la anon."
    if "invalid api key" in bajo or "jwt" in bajo:
        return "La clave SUPABASE_SERVICE_KEY del archivo .env no es válida. Cópiala de nuevo desde Supabase."
    return f"No se pudo guardar: {texto[:200]}"


def explicar_error_registro(e):
    """Convierte el error de Supabase Auth en un mensaje claro para el registro."""
    if isinstance(e, RuntimeError):
        return "Falta configurar SUPABASE_SERVICE_KEY en el archivo .env y reiniciar Flask."
    bajo = str(getattr(e, "message", "") or e).lower()
    if "already" in bajo and ("registered" in bajo or "exists" in bajo):
        return "Ya existe una cuenta con ese correo."
    if "password" in bajo:
        return "La contraseña no cumple los requisitos (mínimo 6 caracteres)."
    if "invalid api key" in bajo or "jwt" in bajo:
        return "La clave SUPABASE_SERVICE_KEY del archivo .env no es válida."
    if "invalid" in bajo and "email" in bajo:
        return "El correo no es válido."
    return "No se pudo crear la cuenta. Revisa los datos e inténtalo de nuevo."


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("signup"))
        return f(*args, **kwargs)
    return wrapper


@app.template_filter("fecha")
def formato_fecha(valor):
    """Muestra las fechas como 31/12/2026 en vez de 2026-12-31."""
    if not valor:
        return ""
    try:
        return date.fromisoformat(str(valor)[:10]).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return valor


@app.template_global("plazo")
def plazo(valor):
    """Estado del plazo de devolución: None si no hay fecha límite válida."""
    try:
        limite = date.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None

    dias = (limite - date.today()).days
    if dias < 0:
        atraso = abs(dias)
        return {
            "texto": f"Vencido hace {atraso} día{'' if atraso == 1 else 's'}",
            "clase": "danger",
            "dias": dias,
        }
    if dias == 0:
        return {"texto": "Vence hoy", "clase": "warning", "dias": 0}
    return {
        "texto": f"Faltan {dias} día{'' if dias == 1 else 's'}",
        "clase": "success",
        "dias": dias,
    }


# ---------------------------------------------------------------------------
# Libros (tabla "libros" en Supabase)
# ---------------------------------------------------------------------------
POR_PAGINA = 24  # libros por página en Libros e Historial


def limpiar_busqueda(texto):
    """Quita caracteres que rompen el filtro de Supabase."""
    return re.sub(r'[,()%*\\"]', " ", texto or "").strip()


def buscar_libros(q="", mueble="", seccion="", estado="", pagina=1, por_pagina=POR_PAGINA):
    """Devuelve (lista_de_libros, total, hubo_error)."""
    try:
        consulta = supabase_client().table("libros").select("*", count="exact")

        q = limpiar_busqueda(q)
        if q:
            patron = f'"%{q}%"'
            consulta = consulta.or_(
                f"titulo.ilike.{patron},autor.ilike.{patron},editorial.ilike.{patron}"
            )
        if mueble:
            consulta = consulta.eq("mueble", mueble)
        if seccion:
            consulta = consulta.eq("seccion", seccion)
        if estado == "Prestado":
            # "Prestado" = tiene al menos una copia prestada
            ids = ids_con_prestamos()
            if not ids:
                return [], 0, False
            consulta = consulta.in_("id", ids)
        elif estado:
            consulta = consulta.eq("estado", estado)

        desde = (pagina - 1) * por_pagina
        respuesta = (
            consulta.order("titulo").order("id")
            .range(desde, desde + por_pagina - 1)
            .execute()
        )
        return respuesta.data, (respuesta.count or 0), False
    except Exception as e:
        print("ERROR BUSCAR LIBROS:", repr(e))
        return [], 0, True


_FILTROS = None


def opciones_filtros():
    """Lista de muebles y secciones para los filtros (se calcula una vez)."""
    global _FILTROS
    if _FILTROS is None:
        try:
            muebles, secciones = set(), set()
            desde = 0
            while True:
                filas = (
                    supabase_client().table("libros").select("mueble,seccion")
                    .range(desde, desde + 999).execute().data
                )
                for fila in filas:
                    if fila.get("mueble"):
                        muebles.add(fila["mueble"])
                    if fila.get("seccion"):
                        secciones.add(fila["seccion"])
                if len(filas) < 1000:
                    break
                desde += 1000
            _FILTROS = (
                sorted(muebles, key=lambda m: int(re.sub(r"\D", "", m) or 0)),
                sorted(secciones),
            )
        except Exception as e:
            print("ERROR FILTROS:", repr(e))
            return [], []
    return _FILTROS


def numero_pagina():
    try:
        return max(1, int(request.args.get("pagina", 1)))
    except ValueError:
        return 1


# ---------------------------------------------------------------------------
# Préstamos por copia (tabla "prestamos"; solo el servidor la lee y escribe)
# Cada fila es UNA copia prestada. Al devolverla, la fila se borra.
# ---------------------------------------------------------------------------
def obtener_libro(libro_id):
    try:
        datos = (
            supabase_client().table("libros").select("*")
            .eq("id", libro_id).limit(1).execute().data
        )
        return datos[0] if datos else None
    except Exception as e:
        print("ERROR OBTENER LIBRO:", repr(e))
        return None


def prestamos_de_libro(libro_id):
    """Copias prestadas (sin devolver) de un libro, ordenadas por número de copia."""
    return (
        supabase_admin().table("prestamos").select("*")
        .eq("libro_id", libro_id).order("copia").execute().data
    )


def ids_con_prestamos():
    """Ids de los libros que tienen al menos una copia prestada."""
    filas = supabase_admin().table("prestamos").select("libro_id").execute().data
    return sorted({f["libro_id"] for f in filas})


def contar_prestadas(ids):
    """{libro_id: cuántas copias tiene prestadas} para una lista de libros."""
    if not ids:
        return {}
    filas = (
        supabase_admin().table("prestamos").select("libro_id")
        .in_("libro_id", ids).execute().data
    )
    cuenta = {}
    for fila in filas:
        cuenta[fila["libro_id"]] = cuenta.get(fila["libro_id"], 0) + 1
    return cuenta


def actualizar_estado_libro(libro_id, cantidad):
    """El libro queda 'Prestado' solo cuando TODAS sus copias están prestadas."""
    prestadas = len(prestamos_de_libro(libro_id))
    estado = "Prestado" if prestadas >= cantidad else "En Biblioteca"
    supabase_admin().table("libros").update({"estado": estado}).eq("id", libro_id).execute()


def aplicar_prestamo(libro, prestamo_fila):
    """Copia los datos de UN préstamo dentro del dict del libro (para las fichas)."""
    if prestamo_fila:
        libro["estado"] = "Prestado"
        libro["prestado_a"] = prestamo_fila.get("prestado_a")
        libro["curso"] = prestamo_fila.get("curso")
        libro["fecha_prestamo"] = prestamo_fila.get("fecha_prestamo")
        libro["fecha_devolucion"] = prestamo_fila.get("fecha_devolucion")
        libro["copia"] = prestamo_fila.get("copia")
        libro["prestamo_id"] = prestamo_fila.get("id")
    else:
        for campo in ("prestado_a", "curso", "fecha_prestamo", "fecha_devolucion", "copia", "prestamo_id"):
            libro[campo] = None
    return libro


def listar_prestamos(q="", pagina=1, por_pagina=POR_PAGINA):
    """Copias prestadas, cada una con los datos de su libro.
    Devuelve (lista, total, hubo_error). La lista tiene el mismo formato que un libro
    (titulo, autor, mueble, prestado_a, curso, fecha_devolucion...) más 'copia' y 'prestamo_id'."""
    try:
        consulta = supabase_admin().table("prestamos").select("*, libros(*)", count="exact")

        q = limpiar_busqueda(q)
        if q:
            patron = f'"%{q}%"'
            condiciones = [f"prestado_a.ilike.{patron}", f"curso.ilike.{patron}"]
            coincidencias = (
                supabase_client().table("libros").select("id")
                .or_(f"titulo.ilike.{patron},autor.ilike.{patron},editorial.ilike.{patron}")
                .limit(300).execute().data
            )
            if coincidencias:
                ids = ",".join(str(c["id"]) for c in coincidencias)
                condiciones.append(f"libro_id.in.({ids})")
            consulta = consulta.or_(",".join(condiciones))

        desde = (pagina - 1) * por_pagina
        respuesta = (
            consulta.order("fecha_devolucion").order("id")
            .range(desde, desde + por_pagina - 1).execute()
        )

        lista = []
        for fila in respuesta.data:
            libro = dict(fila.get("libros") or {})
            libro["id"] = fila["libro_id"]
            aplicar_prestamo(libro, fila)
            lista.append(libro)
        return lista, (respuesta.count or 0), False
    except Exception as e:
        print("ERROR LISTAR PRESTAMOS:", repr(e))
        return [], 0, True


# Carpeta donde se guardarán las portadas subidas (ruta absoluta)
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'img', 'portadas')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

EXTENSIONES_PERMITIDAS = {"png", "jpg", "jpeg", "gif", "webp"}


def extension_valida(nombre):
    return "." in nombre and nombre.rsplit(".", 1)[1].lower() in EXTENSIONES_PERMITIDAS


@app.route('/')
def inicio():
    prestados = []
    if "user_id" in session:
        prestados, _, _ = listar_prestamos(por_pagina=8)
    return render_template("inicio.html", prestados=prestados)


@app.route('/info', methods=['GET', 'POST'])
@login_required
def info():
    global _FILTROS

    # GET: muestra la información de un libro y sus copias prestadas
    if request.method == 'GET':
        libro_id = request.args.get("libro_id", "").strip()
        if not libro_id:
            return redirect(url_for("libros"))

        libro = obtener_libro(libro_id)
        if not libro:
            flash("No se encontró el libro.", "danger")
            return redirect(url_for("libros"))

        try:
            prestamos = prestamos_de_libro(libro["id"])
        except Exception as e:
            print("ERROR PRESTAMOS DEL LIBRO:", repr(e))
            flash(explicar_error_guardado(e), "danger")
            prestamos = []

        cantidad = libro.get("cantidad") or 1
        return render_template(
            "Infolibro.html",
            libro=libro, prestamos=prestamos,
            disponibles=max(0, cantidad - len(prestamos)),
        )

    # POST: guarda un libro nuevo
    titulo = request.form.get("titulo", "").strip()
    if not titulo:
        flash("Escribe el título del libro.", "danger")
        return redirect(url_for("nuevo_libro"))

    codigo = request.form.get("codigo_barra", "").strip()

    # Evita guardar dos libros con el mismo código de barras
    if codigo:
        try:
            repetido = (
                supabase_client().table("libros").select("id")
                .eq("codigo_barra", codigo).limit(1).execute().data
            )
        except Exception as e:
            print("ERROR REVISANDO CODIGO:", repr(e))
            repetido = []
        if repetido:
            flash(f"Ya existe un libro con el código de barras {codigo}.", "danger")
            return redirect(url_for("nuevo_libro"))

    # Portada (opcional)
    imagen = None
    portada = request.files.get("portada")
    if portada and portada.filename != "" and extension_valida(portada.filename):
        # Prefijo único para que dos archivos con el mismo nombre no se sobrescriban
        nombre_archivo = f"{uuid.uuid4().hex}_{secure_filename(portada.filename)}"
        portada.save(os.path.join(app.config["UPLOAD_FOLDER"], nombre_archivo))
        imagen = f"portadas/{nombre_archivo}"  # se muestra como static/img/<imagen>

    libro = {
        "titulo": titulo,
        "autor": request.form.get("autor", "").strip() or None,
        "editorial": request.form.get("editorial", "").strip() or None,
        "codigo_barra": codigo or None,
        "mueble": request.form.get("mueble", "").strip() or None,
        "seccion": request.form.get("seccion", "").strip() or None,
        # Un libro nuevo siempre empieza disponible: los préstamos se registran en la pantalla Préstamo
        "estado": "En Biblioteca",
        # Copias del libro (mínimo 1, máximo 500)
        "cantidad": min(500, max(1, request.form.get("cantidad", default=1, type=int))),
    }
    if imagen:
        libro["imagen"] = imagen

    try:
        supabase_admin().table("libros").insert(libro).execute()
    except Exception as e:
        print("ERROR GUARDAR LIBRO:", repr(e))
        flash(explicar_error_guardado(e), "danger")
        return redirect(url_for("nuevo_libro"))

    _FILTROS = None  # para que las listas de mueble/sección se actualicen
    flash(f'Libro "{titulo}" guardado correctamente.', "success")
    return redirect(url_for("libros", q=titulo))


@app.post("/eliminar")
@login_required
def eliminar_libro():
    """Quita un libro de la biblioteca (se borra de la tabla libros)."""
    global _FILTROS

    libro_id = request.form.get("libro_id", "").strip()
    if not libro_id:
        return redirect(url_for("libros"))

    libro = obtener_libro(libro_id)
    if not libro:
        flash("No se encontró el libro.", "danger")
        return redirect(url_for("libros"))

    # Un libro con copias prestadas no se puede quitar hasta que las devuelvan
    try:
        prestadas = len(prestamos_de_libro(libro_id))
    except Exception as e:
        print("ERROR REVISANDO PRESTAMOS:", repr(e))
        flash(explicar_error_guardado(e), "danger")
        return redirect(url_for("libros"))

    if prestadas:
        flash(
            f"Este libro tiene {prestadas} copia{'' if prestadas == 1 else 's'} prestada{'' if prestadas == 1 else 's'}. "
            "Devuélvelas antes de quitarlo.",
            "danger",
        )
        return redirect(url_for("info", libro_id=libro_id))

    try:
        supabase_admin().table("libros").delete().eq("id", libro_id).execute()
    except Exception as e:
        print("ERROR QUITAR LIBRO:", repr(e))
        flash(explicar_error_guardado(e), "danger")
        return redirect(url_for("info", libro_id=libro_id))

    # Borra también la portada si fue subida desde la app (carpeta portadas)
    imagen = libro.get("imagen") or ""
    if imagen.startswith("portadas/"):
        ruta = os.path.join(app.config["UPLOAD_FOLDER"], os.path.basename(imagen))
        try:
            if os.path.isfile(ruta):
                os.remove(ruta)
        except OSError as e:
            print("NO SE PUDO BORRAR LA PORTADA:", repr(e))

    _FILTROS = None  # para que las listas de mueble/sección se actualicen
    flash(f'"{libro["titulo"]}" fue quitado de la biblioteca.', "success")
    return redirect(url_for("libros"))


@app.route('/register', methods=["GET", "POST"])
def register():
    """Crea la cuenta en Supabase Auth ya confirmada (sin correo) y entra directo a la página."""
    if "user_id" in session:
        return redirect(url_for("inicio"))

    if request.method == "GET":
        return render_template("CrearCuenta.html")

    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirmar = request.form.get("confirm_password", "")

    def error(mensaje):
        return render_template(
            "CrearCuenta.html", error=mensaje, nombre=nombre, email=email
        ), 400

    if not nombre or not email or not password:
        return error("Completa todos los campos.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return error("Escribe un correo válido.")
    if len(password) < 6:
        return error("La contraseña debe tener al menos 6 caracteres.")
    if password != confirmar:
        return error("Las contraseñas no coinciden.")

    # 1) Crear el usuario en Authentication → Users, ya confirmado
    try:
        supabase_admin().auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"nombre": nombre},
        })
    except Exception as e:
        print("ERROR REGISTRO:", repr(e))
        return error(explicar_error_registro(e))

    # 2) Iniciar sesión automáticamente con la cuenta recién creada
    try:
        respuesta = supabase_client().auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        if respuesta.user is None:
            raise ValueError("Sin usuario")
    except Exception as e:
        print("ERROR LOGIN TRAS REGISTRO:", repr(e))
        flash("Cuenta creada. Inicia sesión con tu correo y contraseña.", "success")
        return redirect(url_for("signup"))

    session.clear()
    session.permanent = True
    session["user_id"] = str(respuesta.user.id)
    session["email"] = respuesta.user.email
    session["nombre"] = nombre
    flash(f"Cuenta creada. ¡Bienvenido, {nombre}!", "success")
    return redirect(url_for("inicio"))


@app.route('/signup', methods=["GET", "POST"])
def signup():
    # Si ya tiene sesión, no tiene sentido mostrar el login
    if "user_id" in session:
        return redirect(url_for("inicio"))

    if request.method == "GET":
        return render_template("IniciarSesion.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template(
            "IniciarSesion.html",
            error="Escribe tu email y contraseña"
        ), 400

    try:
        response = supabase_client().auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        if response.user is None:
            raise ValueError("Sin usuario")
    except Exception as e:
        print("ERROR LOGIN:", repr(e))
        if "not confirmed" in str(e).lower():
            mensaje = "Esta cuenta no está confirmada. Crea una cuenta nueva desde la página."
        else:
            mensaje = "Email o contraseña incorrectos"
        return render_template("IniciarSesion.html", error=mensaje), 401

    session.clear()
    session.permanent = True
    session['user_id'] = str(response.user.id)
    session['email'] = response.user.email
    session["nombre"] = (response.user.user_metadata or {}).get("nombre")
    return redirect(url_for("inicio"))


@app.route('/libros')
@login_required
def libros():
    q = request.args.get("q", "").strip()
    mueble = request.args.get("mueble", "")
    seccion = request.args.get("seccion", "")
    estado = request.args.get("estado", "")
    pagina = numero_pagina()

    lista, total, hubo_error = buscar_libros(q, mueble, seccion, estado, pagina)
    muebles, secciones = opciones_filtros()

    # Cuántas copias de cada libro están prestadas (para mostrar las disponibles)
    try:
        cuentas = contar_prestadas([l["id"] for l in lista])
        for l in lista:
            l["prestadas"] = cuentas.get(l["id"], 0)
    except Exception as e:
        print("ERROR CONTANDO PRESTADAS:", repr(e))
        for l in lista:
            l["prestadas"] = None

    return render_template(
        "Libros.html",
        libros=lista, total=total, hubo_error=hubo_error,
        q=q, mueble=mueble, seccion=seccion, estado=estado,
        muebles=muebles, secciones=secciones,
        pagina=pagina, total_paginas=max(1, math.ceil(total / POR_PAGINA)),
    )


@app.route('/prestamo', methods=["GET", "POST"])
@login_required
def prestamo():
    libro_id = request.values.get("libro_id", "").strip()
    if not libro_id:
        flash("Primero escanea un libro para prestarlo.", "danger")
        return redirect(url_for("escaneo_libro"))

    libro = obtener_libro(libro_id)
    if not libro:
        flash("No se encontró el libro.", "danger")
        return redirect(url_for("escaneo_libro"))

    cantidad = libro.get("cantidad") or 1

    # Copias que ya están prestadas -> solo se pueden elegir las libres
    try:
        prestadas = {p["copia"] for p in prestamos_de_libro(libro_id)}
    except Exception as e:
        print("ERROR PRESTAMOS DEL LIBRO:", repr(e))
        flash(explicar_error_guardado(e), "danger")
        return redirect(url_for("info", libro_id=libro_id))

    libres = [n for n in range(1, cantidad + 1) if n not in prestadas]
    if not libres:
        flash("Este libro no tiene copias disponibles: todas están prestadas. Devuelve una para prestarla de nuevo.", "danger")
        return redirect(url_for("info", libro_id=libro_id))

    hoy = date.today().isoformat()

    if request.method == "GET":
        return render_template("prestamo.html", libro=libro, copias=libres, hoy=hoy)

    # POST: guardar el préstamo
    prestado_a = request.form.get("prestado_a", "").strip()
    curso = request.form.get("curso", "").strip()
    fecha_limite = request.form.get("fecha_devolucion", "").strip()
    copia = request.form.get("copia", type=int)

    if not prestado_a or not curso or not fecha_limite:
        flash("Completa todos los campos del préstamo.", "danger")
        return redirect(url_for("prestamo", libro_id=libro_id))

    if copia not in libres:
        flash("Elige una copia disponible.", "danger")
        return redirect(url_for("prestamo", libro_id=libro_id))

    try:
        limite = date.fromisoformat(fecha_limite)
    except ValueError:
        flash("La fecha límite no es válida.", "danger")
        return redirect(url_for("prestamo", libro_id=libro_id))

    if limite < date.today():
        flash("La fecha límite no puede ser anterior a hoy.", "danger")
        return redirect(url_for("prestamo", libro_id=libro_id))

    try:
        respuesta = supabase_admin().table("prestamos").insert({
            "libro_id": int(libro_id),
            "copia": copia,
            "prestado_a": prestado_a,
            "curso": curso,
            "fecha_prestamo": hoy,
            "fecha_devolucion": limite.isoformat(),
        }).execute()
        actualizar_estado_libro(libro_id, cantidad)
    except Exception as e:
        print("ERROR GUARDAR PRESTAMO:", repr(e))
        if "duplicate" in str(e).lower() or "23505" in str(e):
            flash(f"La copia {copia} ya está prestada. Elige otra.", "danger")
        else:
            flash(explicar_error_guardado(e), "danger")
        return redirect(url_for("prestamo", libro_id=libro_id))

    nuevo = respuesta.data[0] if respuesta.data else {}

    # Después de guardar, se abre la ficha de resumen de ESA copia
    return redirect(url_for("tarjeta_resumen", libro_id=libro_id, prestamo_id=nuevo.get("id"), nuevo=1))


@app.post("/devolver")
@login_required
def devolver():
    """Devuelve UNA copia: sale del Historial y de Inicio (y se borra el préstamo)."""
    prestamo_id = request.form.get("prestamo_id", type=int)
    libro_id = request.form.get("libro_id", "").strip()

    try:
        if prestamo_id:
            filas = (
                supabase_admin().table("prestamos").select("*")
                .eq("id", prestamo_id).limit(1).execute().data
            )
        elif libro_id:
            filas = prestamos_de_libro(libro_id)
            if len(filas) > 1:
                flash("Este libro tiene varias copias prestadas. Elige cuál se devuelve.", "danger")
                return redirect(url_for("info", libro_id=libro_id))
        else:
            filas = []

        if not filas:
            flash("No se encontró ese préstamo.", "danger")
            return redirect(url_for("historial"))

        fila = filas[0]
        libro = obtener_libro(fila["libro_id"]) or {}
        cantidad = libro.get("cantidad") or 1

        supabase_admin().table("prestamos").delete().eq("id", fila["id"]).execute()
        actualizar_estado_libro(fila["libro_id"], cantidad)
    except Exception as e:
        print("ERROR DEVOLVER:", repr(e))
        flash(explicar_error_guardado(e), "danger")
        if libro_id:
            return redirect(url_for("info", libro_id=libro_id))
        return redirect(url_for("historial"))

    titulo = libro.get("titulo") or "El libro"
    flash(f'"{titulo}" (copia {fila["copia"]}) fue devuelto correctamente.', "success")
    return redirect(url_for("historial"))


@app.route('/cuenta')
@login_required
def cuenta():
    nombre = session.get("nombre")
    if not nombre:
        # Sesiones iniciadas antes de guardar el nombre: se lee desde Supabase
        try:
            usuario = supabase_admin().auth.admin.get_user_by_id(session["user_id"]).user
            nombre = (usuario.user_metadata or {}).get("nombre")
            if nombre:
                session["nombre"] = nombre
        except Exception as e:
            print("ERROR NOMBRE CUENTA:", repr(e))

    return render_template(
        "Cuenta.html",
        nombre=nombre or "No registrado",
        email=session.get("email", ""),
    )


@app.route('/nuevo')
@login_required
def nuevo_libro():
    muebles, secciones = opciones_filtros()
    return render_template("NuevoLibro.html", muebles=muebles, secciones=secciones)


@app.route('/resumen')
@login_required
def tarjeta_resumen():
    libro_id = request.args.get("libro_id", "").strip()
    if not libro_id:
        return redirect(url_for("historial"))

    libro = obtener_libro(libro_id)
    if not libro:
        flash("No se encontró el libro.", "danger")
        return redirect(url_for("historial"))

    # Ficha de UNA copia: la indicada en la dirección o, si no, la última prestada
    try:
        prestamos = prestamos_de_libro(libro_id)
    except Exception as e:
        print("ERROR RESUMEN PRESTAMOS:", repr(e))
        prestamos = []

    elegido = None
    prestamo_id = request.args.get("prestamo_id", type=int)
    if prestamo_id:
        elegido = next((p for p in prestamos if p["id"] == prestamo_id), None)
    if not elegido and prestamos:
        elegido = max(prestamos, key=lambda p: p["id"])
    aplicar_prestamo(libro, elegido)

    return render_template(
        "resumen.html",
        libro=libro,
        nuevo=request.args.get("nuevo") == "1",
    )


@app.route('/historial')
@login_required
def historial():
    q = request.args.get("q", "").strip()
    pagina = numero_pagina()

    lista, total, hubo_error = listar_prestamos(q, pagina)

    return render_template(
        "Historial.html",
        libros=lista, total=total, hubo_error=hubo_error, q=q,
        pagina=pagina, total_paginas=max(1, math.ceil(total / POR_PAGINA)),
    )


@app.route('/escaneo')
@login_required
def escaneo_libro():
    """Pantalla de escaneo: no muestra ningún libro hasta que se escanea un código."""
    codigo = limpiar_busqueda(request.args.get("codigo", ""))
    libro = None
    no_encontrado = False
    hubo_error = False

    if codigo:
        try:
            respuesta = (
                supabase_client().table("libros").select("*")
                .or_(f'codigo_barra.eq."{codigo}",isbn.eq."{codigo}"')
                .limit(1).execute()
            )
            if respuesta.data:
                libro = respuesta.data[0]
                try:
                    prestamos = prestamos_de_libro(libro["id"])
                except Exception as e:
                    print("ERROR ESCANEO PRESTAMOS:", repr(e))
                    prestamos = []
                aplicar_prestamo(libro, max(prestamos, key=lambda p: p["id"]) if prestamos else None)
            else:
                no_encontrado = True
        except Exception as e:
            print("ERROR ESCANEO:", repr(e))
            hubo_error = True

    return render_template(
        "escaneo_libro.html",
        libro=libro, codigo=codigo,
        no_encontrado=no_encontrado, hubo_error=hubo_error,
    )


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("signup"))


if __name__ == "__main__":
    app.run(debug=True)