# -*- coding: utf-8 -*-
# =====================================================================
# compiler.py - Compilador de BrickScript (Python 2.7)
#
# FLUJO COMPLETO:   archivo .brick  --lexer-->  lista de TOKENS
#                   TOKENS --Parser--> AST (un diccionario de Python)
#                   AST --json.dump--> archivo .json  (lo lee runtime.py)
#
# REGLA DE ORO (retrocompatibilidad): todo lo nuevo es OPCIONAL.
# Si el .brick viejo no trae FORM ni LEVELS, el .json sale igual que antes.
# =====================================================================

import sys
import re
import json

# Palabras permitidas dentro de un bloque LEVEL. Si manana quieres un atributo
# nuevo (ej. BONUS), lo agregas AQUI y el runtime lo lee del JSON en minuscula.
CLAVES_NIVEL = ('SPEED', 'NEXT_AT', 'POISON', 'INVULNERABLE', 'CLOUDS', 'NYAN')

# Valores permitidos para FORM dentro de DEFINE SHAPE.
FORMAS_VALIDAS = ('RECTANGULAR', 'CIRCULAR', 'TRIANGULAR')


# ---------------------------------------------------------------------
# 1) LEXER: convierte el texto en una lista de "palabras" (tokens)
# ---------------------------------------------------------------------
def lexer(codigo_fuente):
    # Paso 1: borrar comentarios. Un comentario empieza con '#', PERO los
    # colores tambien (#FF8C00). El "(?![0-9A-Fa-f]{6}\b)" significa:
    # "no es comentario si despues del # vienen 6 digitos hexadecimales".
    codigo_fuente = re.sub(r'(?m)(^|\s)#(?![0-9A-Fa-f]{6}\b).*', ' ', codigo_fuente)

    # Paso 2: la expresion regular define QUE es un token. Se prueba en orden:
    token_regex = (r'#[0-9A-Fa-f]{6}\b'          # un color: #33CC33
                   r'|\b[A-F0-9]{6}\b'           # color sin '#'
                   r'|\b[A-Z][A-Z0-9_]*\b'       # palabra clave/nombre: LEVELS, NYAN_CAT
                   r'|\d+'                       # un numero entero: 150
                   r'|[\[\](),:]')               # simbolos sueltos: [ ] ( ) , :
    # findall devuelve TODOS los tokens en orden. Todo lo demas (espacios,
    # minusculas, simbolos raros) se ignora.
    return re.findall(token_regex, codigo_fuente)


# ---------------------------------------------------------------------
# 2) PARSER: recorre los tokens y arma el AST
# ---------------------------------------------------------------------
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.posicion = 0           # "dedo" que senala el token actual
        # El AST es lo que terminara dentro del .json. Las claves que existen
        # aqui desde el inicio son las que siempre salen en el JSON.
        self.ast = {
            "tipo_juego": None,
            "config": {},
            "shapes": {},
            "events": {},
            "shape_attrs": {},      # color/chance/form por pieza
            "powerups": {}          # solo Tetris
        }

    def parse(self):
        # Mira el token actual y decide a que funcion mandarlo.
        # Cada rama corresponde a una "regla" de la gramatica (.bnf).
        while self.posicion < len(self.tokens):
            t = self.tokens[self.posicion]
            if t == 'GAME_TYPE':
                self.parsear_tipo_juego()
            elif t == 'GAME_GRID':
                self.parsear_grid()
            elif t == 'GAME_COLOR':
                self.consumir('GAME_COLOR')
                self.ast['config']['color'] = self.consumir()
            elif t == 'DEFINE':
                self.parsear_definicion()
            elif t == 'LEVELS':            # <-- NUEVO (Actividad 4)
                self.parsear_levels()
            elif t == 'ON':
                self.parsear_evento()
            else:
                self.posicion += 1         # token desconocido a nivel raiz: se salta

        # Limpieza para retrocompatibilidad: si el juego NO es Tetris, quitamos
        # las claves que no le sirven. Asi snake.json sale identico al original.
        if self.ast['tipo_juego'] != 'TETRIS':
            del self.ast['powerups']
            if not self.ast['shape_attrs']:
                del self.ast['shape_attrs']
        return self.ast

    # --- utilidades -------------------------------------------------
    def actual(self):
        # Devuelve el token donde esta el dedo SIN avanzar (None si se acabo).
        if self.posicion < len(self.tokens):
            return self.tokens[self.posicion]
        return None

    def consumir(self, esperado=None):
        # Devuelve el token actual Y avanza el dedo. Si 'esperado' esta dado
        # y no coincide -> ERROR DE SINTAXIS (asi se detectan los errores).
        if self.posicion < len(self.tokens):
            token = self.tokens[self.posicion]
            if esperado and token != esperado:
                raise Exception("Error de sintaxis: Se esperaba '" + esperado +
                                "' pero se encontro '" + token + "'")
            self.posicion += 1
            return token
        if esperado:
            raise Exception("Error de sintaxis: Se esperaba '" + esperado +
                            "' pero se llego al final del archivo.")
        return None

    def consumir_numero(self, contexto):
        # Igual que consumir(), pero exige que el token sea un numero.
        t = self.consumir()
        if t is None or not t.isdigit():
            raise Exception("Error de sintaxis: se esperaba un numero en " +
                            contexto + " pero se encontro '" + str(t) + "'")
        return int(t)

    def normalizar_color(self, c):
        return c if c.startswith('#') else '#' + c

    # --- reglas simples --------------------------------------------
    def parsear_tipo_juego(self):
        self.consumir('GAME_TYPE')
        self.ast['tipo_juego'] = self.consumir()

    def parsear_grid(self):
        self.consumir('GAME_GRID')
        self.consumir('(')
        ancho = int(self.consumir())
        self.consumir(',')
        alto = int(self.consumir())
        self.consumir(')')
        self.ast['config']['grid_size'] = [ancho, alto]

    # --- DEFINE SHAPE / POWERUP ------------------------------------
    def parsear_estados(self):
        # STATE 1: [..] [..]  STATE 2: ...  ->  lista de matrices
        estados = []
        while self.actual() == 'STATE':
            self.consumir('STATE')
            self.consumir()                 # numero del estado (no se guarda)
            self.consumir(':')
            matriz = []
            while self.actual() == '[':
                fila = []
                self.consumir('[')
                while self.actual() != ']':
                    fila.append(int(self.consumir()))
                    if self.actual() == ',':
                        self.consumir(',')
                self.consumir(']')
                matriz.append(fila)
            estados.append(matriz)
        return estados

    def parsear_definicion(self):
        self.consumir('DEFINE')
        tipo = self.consumir()
        if tipo == 'SHAPE':
            self.parsear_shape()
        elif tipo == 'POWERUP':
            self.parsear_powerup()
        else:
            raise Exception("Error de sintaxis: Se esperaba 'SHAPE' o 'POWERUP' "
                            "despues de DEFINE, se encontro '" + str(tipo) + "'")

    def parsear_shape(self):
        nombre = self.consumir()
        self.consumir(':')
        # 'attrs' lleva TODOS los atributos con valores por defecto (para Tetris).
        # 'explicitos' solo lo que el programador escribio (para Snake).
        attrs = {"color": "#00FFFF", "chance": 1}
        explicitos = {}
        # <-- NUEVO: 'FORM' se agrega a la lista de atributos aceptados.
        while self.actual() in ('COLOR', 'CHANCE', 'FORM'):
            clave = self.consumir()
            self.consumir(':')
            valor = self.consumir()
            if clave == 'COLOR':
                attrs['color'] = explicitos['color'] = self.normalizar_color(valor)
            elif clave == 'CHANCE':
                attrs['chance'] = explicitos['chance'] = int(valor)
            else:                                   # FORM
                if valor not in FORMAS_VALIDAS:
                    raise Exception("Error de sintaxis: FORM debe ser RECTANGULAR, "
                                    "CIRCULAR o TRIANGULAR, se encontro '" + str(valor) + "'")
                attrs['form'] = explicitos['form'] = valor
        estados = self.parsear_estados()
        self.consumir('END')
        self.ast['shapes'][nombre] = estados
        if self.ast['tipo_juego'] == 'TETRIS':
            self.ast['shape_attrs'][nombre] = attrs
        elif explicitos:
            # Snake: solo se guarda lo escrito. Si no escribiste nada, no sale
            # 'shape_attrs' (asi el snake.json viejo queda identico).
            self.ast['shape_attrs'][nombre] = explicitos

    def parsear_powerup(self):
        nombre = self.consumir()
        self.consumir(':')
        pu = {"puntos": 0, "color": "#FFFFFF"}
        while self.actual() in ('COLOR', 'EFFECT', 'POINTS', 'TRIGGER_LINES', 'TRIGGER_ROTATE'):
            clave = self.consumir()
            self.consumir(':')
            if clave == 'COLOR':
                pu['color'] = self.normalizar_color(self.consumir())
            elif clave == 'EFFECT':
                pu['efecto'] = self.consumir()
            elif clave == 'POINTS':
                pu['puntos'] = int(self.consumir())
            elif clave == 'TRIGGER_LINES':
                pu['trigger_lineas'] = int(self.consumir())
            elif clave == 'TRIGGER_ROTATE':
                shape = self.consumir()
                veces = int(self.consumir())
                pu['trigger_rotacion'] = {"shape": shape, "veces": veces}
        pu['estados'] = self.parsear_estados()
        self.consumir('END')
        self.ast['powerups'][nombre] = pu

    # --- LEVELS (NUEVO, Actividad 4) -------------------------------
    def parsear_levels(self):
        # Forma esperada:
        #   LEVELS:
        #     LEVEL NOMBRE:
        #       CLAVE: numero
        #       ...
        #     END          <- cierra el LEVEL
        #   END            <- cierra LEVELS
        self.consumir('LEVELS')
        self.consumir(':')
        niveles = []
        while self.actual() == 'LEVEL':
            self.consumir('LEVEL')
            nivel = {'nombre': self.consumir()}
            self.consumir(':')
            while self.actual() != 'END':
                if self.actual() is None:
                    raise Exception("Error de sintaxis: falta 'END' al final del nivel " +
                                    nivel['nombre'])
                clave = self.consumir()
                if clave not in CLAVES_NIVEL:
                    raise Exception("Error de sintaxis: atributo de nivel desconocido '" +
                                    clave + "' en el nivel " + nivel['nombre'])
                self.consumir(':')
                nivel[clave.lower()] = self.consumir_numero(clave + " del nivel " + nivel['nombre'])
            self.consumir('END')                    # END del LEVEL
            if nivel.get('speed', 1) <= 0:
                raise Exception("Error: SPEED del nivel " + nivel['nombre'] + " debe ser mayor que 0")
            niveles.append(nivel)
        if not niveles:
            raise Exception("Error de sintaxis: LEVELS debe contener al menos un LEVEL")
        self.consumir('END')                        # END de LEVELS
        self.ast['levels'] = niveles                # solo existe la clave si hubo LEVELS

    # --- EVENTOS (sin cambios) -------------------------------------
    def parsear_evento(self):
        self.consumir('ON')
        nombre_evento = 'ON_' + self.consumir()
        self.consumir(':')
        acciones = []
        fin_accion = ['END', 'ON', 'DEFINE', 'SPAWN', 'MOVE', 'ROTATE',
                      'INCREASE_SCORE', 'SET_DIRECTION', 'GROW', 'GAME_OVER']
        while self.posicion < len(self.tokens) and self.actual() != 'END':
            verbo = self.consumir()
            if verbo == 'GAME_OVER':
                acciones.append({'accion': verbo, 'objeto': None, 'params': []})
                continue
            objeto = self.consumir()
            params = []
            if self.actual() == 'AT':
                self.consumir('AT')
                if self.actual() == 'RANDOM':
                    params.append(self.consumir())
                else:
                    self.consumir('(')
                    x = int(self.consumir())
                    self.consumir(',')
                    y = int(self.consumir())
                    self.consumir(')')
                    params.append([x, y])
            elif self.actual() is not None and self.actual() not in fin_accion:
                params.append(self.consumir())
            acciones.append({'accion': verbo, 'objeto': objeto, 'params': params})
        self.consumir('END')
        self.ast['events'][nombre_evento] = acciones


# ---------------------------------------------------------------------
# 3) GENERADOR: escribe el AST en un archivo .json
# ---------------------------------------------------------------------
def generar_codigo(ast, archivo_salida):
    f = open(archivo_salida, 'w')
    try:
        json.dump(ast, f, indent=2)
    finally:
        f.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python compiler.py <archivo_entrada.brick>")
        sys.exit(1)
    archivo_entrada = sys.argv[1]
    archivo_salida = archivo_entrada.replace('.brick', '.json')
    print("Compilando " + archivo_entrada + "...")
    try:
        f = open(archivo_entrada, 'r')
        try:
            codigo = f.read()
        finally:
            f.close()
        ast = Parser(lexer(codigo)).parse()
        generar_codigo(ast, archivo_salida)
        print("Compilacion exitosa! Archivo de juego creado en " + archivo_salida)
    except Exception as e:
        print("\n!!! ERROR DE COMPILACION !!!")
        print(str(e))
        sys.exit(1)
