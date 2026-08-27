CREATE TABLE IF NOT EXISTS `intermediarios` (
  `id` INT NOT NULL PRIMARY KEY,
  `nombre` VARCHAR(255) NOT NULL,
  `telefono` VARCHAR(50) NOT NULL DEFAULT '',
  `email` VARCHAR(255) NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `clientes` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `nombre` VARCHAR(255) NOT NULL,
  `telefono` VARCHAR(50) NOT NULL DEFAULT '',
  `direccion` VARCHAR(255) NOT NULL DEFAULT '',
  `email` VARCHAR(255) NOT NULL DEFAULT '',
  `intermediario_id` INT NOT NULL DEFAULT 0,
  `notas` VARCHAR(2000) NOT NULL DEFAULT '',
  CONSTRAINT `fk_clientes_intermediarios`
    FOREIGN KEY (`intermediario_id`) REFERENCES `intermediarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `faenas` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `numero` VARCHAR(50) UNIQUE,
  `cliente_id` INT NOT NULL,
  `intermediario_id` INT NOT NULL DEFAULT 0,
  `direccion` VARCHAR(255) NOT NULL DEFAULT '',
  `tipo_trabajo` VARCHAR(255) NOT NULL DEFAULT '',
  `importe` DOUBLE NOT NULL DEFAULT 0,
  `fecha_inicio` VARCHAR(32) NOT NULL DEFAULT '',
  `archivada` TINYINT(1) NOT NULL DEFAULT 0,
  `carpeta` VARCHAR(255) NOT NULL DEFAULT '',
  CONSTRAINT `fk_faenas_clientes`
    FOREIGN KEY (`cliente_id`) REFERENCES `clientes` (`id`),
  CONSTRAINT `fk_faenas_intermediarios`
    FOREIGN KEY (`intermediario_id`) REFERENCES `intermediarios` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `anotaciones` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `faena_id` INT NOT NULL,
  `tipo` VARCHAR(50) NOT NULL DEFAULT 'texto',
  `contenido` VARCHAR(5000) NOT NULL DEFAULT '',
  `fecha` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_anotaciones_faenas`
    FOREIGN KEY (`faena_id`) REFERENCES `faenas` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `materiales` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `nombre` VARCHAR(255) NOT NULL,
  `unidad` VARCHAR(20) NOT NULL DEFAULT 'ud',
  `categoria` VARCHAR(100) NOT NULL DEFAULT 'Herraje',
  `definicion` VARCHAR(5000) NOT NULL DEFAULT ''
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `precios` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `material_id` INT NOT NULL,
  `proveedor` VARCHAR(255) NOT NULL,
  `precio_unitario` DOUBLE NOT NULL,
  `fecha_actualizacion` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uk_precios_material_proveedor` (`material_id`, `proveedor`),
  CONSTRAINT `fk_precios_materiales`
    FOREIGN KEY (`material_id`) REFERENCES `materiales` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `gastos_faena` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `faena_id` INT NOT NULL,
  `tipo` VARCHAR(50) NOT NULL DEFAULT 'otro',
  `descripcion` VARCHAR(5000) NOT NULL DEFAULT '',
  `cantidad` DOUBLE NOT NULL DEFAULT 1,
  `precio_unitario` DOUBLE NOT NULL DEFAULT 0,
  `total` DOUBLE NOT NULL DEFAULT 0,
  `fecha` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `ticket_foto` VARCHAR(500) NOT NULL DEFAULT '',
  CONSTRAINT `fk_gastos_faena`
    FOREIGN KEY (`faena_id`) REFERENCES `faenas` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `presupuestos_faena` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `faena_id` INT NOT NULL,
  `tipo` VARCHAR(50) NOT NULL DEFAULT 'material',
  `descripcion` VARCHAR(5000) NOT NULL DEFAULT '',
  `cantidad` DOUBLE NOT NULL DEFAULT 1,
  `precio_unitario` DOUBLE NOT NULL DEFAULT 0,
  `total` DOUBLE NOT NULL DEFAULT 0,
  `fecha` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_presupuestos_faena`
    FOREIGN KEY (`faena_id`) REFERENCES `faenas` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `fotos_faena` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `faena_id` INT NOT NULL,
  `nombre` VARCHAR(255) NOT NULL,
  `ruta_foto` VARCHAR(500) NOT NULL,
  `fecha` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_fotos_faena`
    FOREIGN KEY (`faena_id`) REFERENCES `faenas` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `book_fotos` (
  `id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `faena_id` INT NOT NULL DEFAULT 0,
  `ruta_foto` VARCHAR(500) NOT NULL,
  `titulo` VARCHAR(255) NOT NULL DEFAULT '',
  `descripcion` VARCHAR(5000) NOT NULL DEFAULT '',
  `fecha` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `orden` INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- intermediarios (1 filas)
INSERT IGNORE INTO `intermediarios` (`id`, `nombre`, `telefono`, `email`) VALUES (0, 'Cliente directo', '', '');
INSERT IGNORE INTO `intermediarios` (`id`, `nombre`, `telefono`, `email`) VALUES (0, 'Cliente directo', '', '');

-- clientes (10 filas)
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (1, 'Lucia Perelo-Roberto', '625342741', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (2, 'Ana Valverde Riola', '685856085', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (3, 'Amparo hna vte rodrigo', '605926678', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (4, 'Katy amiga Maria massanassa', '', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (5, 'Puri', '', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (6, 'Óscar primo Felix', '', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (7, 'Felix', '', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (8, 'Marta Oscar', '604 94 96 07', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (9, 'Marta Oscar', '604 94 96 07', '', 0, '', '');
INSERT IGNORE INTO `clientes` (`id`, `nombre`, `telefono`, `email`, `intermediario_id`, `notas`, `direccion`) VALUES (10, 'Marta Oscar', '604 94 96 07', '', 0, '', '');

-- faenas (15 filas)
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (1, '000101', 1, 0, 'c Menorca 20 Perello', 'Armario plegable', 0.0, '', 1, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000101_Lucia_PereloRoberto');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (2, '000201', 2, 0, 'Pza Constitución 2 1b', 'Cocina', 5200.0, '2026-05-18', 0, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000201_Ana_Valverde_Riola');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (3, '000301', 3, 0, 'C Málaga 39, Catarroja', 'Mueble registro', 370.0, '2026-05-19', 0, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000301_Amparo_hna_vte_rodrigo');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (4, '000401', 4, 0, 'C/Peris y Valero 54- 6 Catarroja', 'Cortar alto nevera', 100.0, '2026-05-19', 1, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000401_Katy_amiga_Maria_massanassa');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (5, '000501', 5, 0, 'avda  corts valencianes 121 pta 14.Albal', 'Tapajuntas y estantes', 450.0, '2026-05-19', 0, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000501_Puri');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (6, '000601', 6, 0, 'Fco Larrode 10 522', 'Rodapié', 890.0, '2026-05-20', 0, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000601_Óscar_primo_Felix');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (7, '000701', 7, 0, '', 'Registros escalera', 90.0, '2026-05-22', 0, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000701_Felix');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (8, '000302', 3, 0, '', 'Armario', 0.0, '2026-06-28', 0, 'c:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000302_Amparo_hna_vte_rodrigo');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (9, '000602', 6, 0, '', 'Puerta', 70.0, '2026-06-20', 1, 'c:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000602_Óscar_primo_Felix');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (10, '000801', 8, 0, 'C Asturias 7.Catarroja', 'Rodapié', 200.0, '2026-06-26', 1, 'c:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000801_Marta_Oscar');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (11, '000603', 6, 0, '', 'Puerta', 70.0, '2026-06-20', 1, 'c:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000603_Óscar_primo_Felix');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (12, '000901', 9, 0, 'C Asturias 7.Catarroja', 'Rodapié', 200.0, '2026-06-26', 1, 'c:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000901_Marta_Oscar');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (13, '000604', 6, 0, '', 'Puerta', 70.0, '2026-06-20', 1, 'c:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000604_Óscar_primo_Felix');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (14, '001001', 10, 0, 'C Asturias 7.Catarroja', 'Rodapié', 200.0, '2026-06-26', 1, 'c:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\001001_Marta_Oscar');
INSERT IGNORE INTO `faenas` (`id`, `numero`, `cliente_id`, `intermediario_id`, `direccion`, `tipo_trabajo`, `importe`, `fecha_inicio`, `archivada`, `carpeta`) VALUES (15, '000802', 8, 0, '', 'Poner rodapié', 250.0, '', 0, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000802_Marta_Oscar');

-- anotaciones (10 filas)
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (1, 1, 'texto', '625342741', '2026-05-12 18:50:07');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (2, 4, 'texto', 'Cortar alto nevera', '2026-05-19 20:04:41');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (3, 5, 'texto', '3 pack 70 ala 10 -40    _____120
9 tap 70x12     -  8    ----- 72
adhesivo 2              ----- 18
              total         210', '2026-05-20 20:43:20');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (5, 5, 'texto', 'tablero       60
corte 20 m    20 
canteado      21
     total    101', '2026-05-20 20:52:47');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (6, 3, 'texto', 'K544 silverjak oak', '2026-05-26T18:12:17.368Z');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (7, 3, 'texto', '6 cm añadir profundidad 
Rodapié 9', '2026-05-26T18:14:20.967Z');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (10, 3, 'texto', 'entregado 100 26/05
', '2026-05-26 18:42:55');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (11, 2, 'texto', '1  Columna HM 2200
1  Columna Despensa 2200x40
1 alto 70x60
2 alto 80x40
2 alto 80x60
2 alto 80x70
1 Bajo freg 80x90
1 Mod horno 80x60
1 Mod bajo  80x40
3 melamina 16
1 tablex 3 mm o simil
2 cc 32x60
1 caj 16x60
5 caj 16x40
2 caj 28x60
34 bisagras rectas clip 
4 bisagras 180 clip
32 patas
1 perfil gola mod sup
2 tiras zocalo aluminio
 
  Lista puertas J Line melamina 

  Sin J
1 Lateral 230x60
1 70x60
2 80x60
2 80x40
1 140x60
1 140x40
1 80x30
1 140x30
 
  Con J

1 45x60
2 80x40
1 80x50
4 80x35
1 16x60
2 32x60
5 16x40
2 28x60


', '2026-05-31 17:22:14');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (16, 7, 'texto', '854x210', '2026-06-26T17:53:06.219Z');
INSERT IGNORE INTO `anotaciones` (`id`, `faena_id`, `tipo`, `contenido`, `fecha`) VALUES (17, 7, 'texto', '854x210', '2026-06-26T17:53:06.219Z');

-- materiales (23 filas)
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (1, 'Kit de montaje de puerta plegable para armarios o vestidores de dos puertas 50 kg máx por sistema', 'ud', 'Herraje', 'kit puerta acordeon Emuca');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (2, 'KIT 5 MOLDURAS 7 ALA 10 LAC BCA UNI', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (3, 'JAMBA LAC BCO DIR 2250X70X12MM', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (4, 'GUARDAVIVO MEL BCO 2600X30X30MM', 'ud', 'Otro', 'Cantonera 3x3 Mel b');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (5, 'SELLADOR ACRILICO P JUNTAS 300ML BCO', 'ud', 'Otro', 'Masilla Acrilica');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (6, 'KIT 5 MOLDURAS 7 ALA 10 LAC BCA UNI', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (7, 'JAMBA LAC BCO DIR 2250X70X12MM', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (8, 'AGPLAST. MELAMINA BLANCA B3002 2440x1220x19 mm.', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (9, 'AGPLAST. MELAMINA BLANCA B3002 2800x2070x19 mm.', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (10, 'CORTE SECCIONADORA', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (11, 'AGPLAST. MELAMINA BLANCA B3002 2440x1220x19 mm.', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (12, 'CANTO PVC BLANCO 1110 MA (B3002 MA) 0,8 x 23', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (13, 'CANTEADO', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (14, 'CORTE SECCIONADORA', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (15, 'CONDENA DESBLOQUEO RED LAT CR SAT', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (16, 'TIRADOR METAL CR MT P-544.128', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (17, 'CONDENA/DESCON RED ACE INOX 30MM', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (18, 'BIS SEGUR INOX 150X82MM MOD 565', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (19, 'P SPRAY ELECTRODOMESTICO 400ML BCO', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (20, 'Sellador acrílico para juntas 300 ml blanco', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (21, 'Pack cianocrilato para superficies no porosas 50 g', 'pack', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (22, 'Madera', 'ud', 'Otro', '');
INSERT IGNORE INTO `materiales` (`id`, `nombre`, `unidad`, `categoria`, `definicion`) VALUES (23, 'Tornillos', 'ud', 'Otro', '');

-- precios (23 filas)
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (1, 1, 'LEROY', 80.33, '2026-05-14 20:35:23');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (2, 2, 'OBRAMAT MASSANASSA', 44.75, '2026-05-27 20:18:28');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (3, 3, 'OBRAMAT MASSANASSA', 7.6, '2026-05-27 20:18:29');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (4, 4, 'OBRAMAT MASSANASSA', 4.4, '2026-05-27 20:18:32');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (5, 5, 'OBRAMAT MASSANASSA', 1.7, '2026-05-27 20:18:32');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (6, 6, 'OBRAMAT MASSANASSA', 44.75, '2026-05-27 20:18:30');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (7, 7, 'OBRAMAT MASSANASSA', 7.6, '2026-05-27 20:18:31');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (10, 8, 'SALIMER PROFESIONALES, S.A.', 12.83, '2026-05-30 17:29:54');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (11, 9, 'SALIMER PROFESIONALES, S.A.', 12.83, '2026-05-30 17:29:54');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (12, 10, 'SALIMER PROFESIONALES, S.A.', 0.9, '2026-05-30 17:29:55');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (13, 11, 'SALIMER PROFESIONALES, S.A.', 12.83, '2026-05-30 17:29:56');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (14, 12, 'SALIMER PROFESIONALES, S.A.', 0.46, '2026-05-30 17:30:00');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (15, 13, 'SALIMER PROFESIONALES, S.A.', 1.3, '2026-05-30 17:30:01');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (16, 14, 'SALIMER PROFESIONALES, S.A.', 0.9, '2026-05-30 17:30:00');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (19, 15, 'OBRAMAT MASSANASSA', 12.84, '2026-06-28 17:21:57');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (20, 16, 'OBRAMAT MASSANASSA', 3.59, '2026-06-28 17:21:57');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (21, 17, 'OBRAMAT MASSANASSA', 6.87, '2026-06-28 17:21:57');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (22, 18, 'OBRAMAT MASSANASSA', 10.01, '2026-06-28 17:21:57');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (23, 19, 'OBRAMAT MASSANASSA', 8.4, '2026-06-28 17:21:57');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (64, 20, 'OBRAMAT Massanassa', 1.8, '2026-07-01 21:15:46');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (65, 21, 'OBRAMAT Massanassa', 9.3, '2026-07-01 21:15:46');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (66, 22, 'TOTAL 12.34 EUR', 3.5, '2026-07-04 22:39:35');
INSERT IGNORE INTO `precios` (`id`, `material_id`, `proveedor`, `precio_unitario`, `fecha_actualizacion`) VALUES (67, 23, 'TOTAL 12.34 EUR', 8.84, '2026-07-04 22:39:35');

-- gastos_faena (55 filas)
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (1, 1, 'herraje', 'Kit de montaje de puerta plegable para armarios o vestidores de dos puertas 50 kg máx por sistema', 1.0, 80.33, 80.33, '2026-05-14 20:34:44', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (6, 5, 'herraje', 'KIT 5 MOLDURAS 7 ALA 10 LAC BCA UNI', 3.0, 44.75, 134.25, '2026-05-27 20:18:30', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (7, 5, 'herraje', 'JAMBA LAC BCO DIR 2250X70X12MM', 9.0, 7.6, 68.39999999999999, '2026-05-27 20:18:31', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (9, 5, 'herraje', 'SELLADOR ACRILICO P JUNTAS 300ML BCO', 2.0, 1.7, 3.4, '2026-05-27 20:18:32', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (13, 1, 'herraje', 'AGPLAST. MELAMINA BLANCA B3002 2440x1220x19 mm.', 1.0, 12.83, 12.83, '2026-05-30 17:29:56', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (15, 1, 'herraje', 'AGPLAST. MELAMINA BLANCA B3002 2800x2070x19 mm.', 1.0, 12.83, 12.83, '2026-05-30 17:29:59', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (17, 1, 'herraje', 'CORTE SECCIONADORA', 53.584, 0.9, 48.22560000000001, '2026-05-30 17:30:00', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (18, 1, 'herraje', 'CANTO PVC BLANCO 1110 MA (B3002 MA) 0,8 x 23', 43.134, 0.46, 19.84164, '2026-05-30 17:30:00', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (19, 1, 'herraje', 'CANTEADO', 43.134, 1.3, 56.074200000000005, '2026-05-30 17:30:01', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (20, 1, 'tablero', 'Cantonera 2800x30x30 mel blanco', 2.0, 4.4, 8.8, '2026-05-30 18:12:38', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (25, 7, 'presupuesto', 'montaje puertas', 1.0, 90.0, 90.0, '2026-06-28 16:59:03', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (26, 6, 'presupuesto', 'Montaje rodapie', 1.0, 400.0, 400.0, '2026-06-28 17:02:45', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (27, 6, 'presupuesto', 'Montaje puertas', 7.0, 70.0, 490.0, '2026-06-28 17:03:15', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (31, 2, 'presupuesto', 'Cocina', 1.0, 5200.0, 5200.0, '2026-06-28 17:06:27', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (32, 1, 'herraje', 'CONDENA DESBLOQUEO RED LAT CR SAT', 1.0, 12.84, 12.84, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (33, 1, 'herraje', 'TIRADOR METAL CR MT P-544.128', 2.0, 3.59, 7.18, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (34, 1, 'herraje', 'CONDENA/DESCON RED ACE INOX 30MM', 1.0, 6.87, 6.87, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (35, 1, 'herraje', 'BIS SEGUR INOX 150X82MM MOD 565', 3.0, 10.01, 30.03, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (36, 1, 'herraje', 'P SPRAY ELECTRODOMESTICO 400ML BCO', 1.0, 8.4, 8.4, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (37, 1, 'herraje', 'CONDENA DESBLOQUEO RED LAT CR SAT', 1.0, 12.84, 12.84, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (38, 1, 'herraje', 'TIRADOR METAL CR MT P-544.128', 2.0, 3.59, 7.18, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (39, 1, 'herraje', 'CONDENA/DESCON RED ACE INOX 30MM', 1.0, 6.87, 6.87, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (40, 1, 'herraje', 'BIS SEGUR INOX 150X82MM MOD 565', 3.0, 10.01, 30.03, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (41, 1, 'herraje', 'P SPRAY ELECTRODOMESTICO 400ML BCO', 1.0, 8.4, 8.4, '2026-06-28 17:20:33', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (42, 1, 'herraje', 'CONDENA DESBLOQUEO RED LAT CR SAT', 1.0, 12.84, 12.84, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (43, 1, 'herraje', 'TIRADOR METAL CR MT P-544.128', 2.0, 3.59, 7.18, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (44, 1, 'herraje', 'CONDENA/DESCON RED ACE INOX 30MM', 1.0, 6.87, 6.87, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (45, 1, 'herraje', 'BIS SEGUR INOX 150X82MM MOD 565', 3.0, 10.01, 30.03, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (46, 1, 'herraje', 'P SPRAY ELECTRODOMESTICO 400ML BCO', 1.0, 8.4, 8.4, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (47, 1, 'herraje', 'CONDENA DESBLOQUEO RED LAT CR SAT', 1.0, 12.84, 12.84, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (48, 1, 'herraje', 'TIRADOR METAL CR MT P-544.128', 2.0, 3.59, 7.18, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (49, 1, 'herraje', 'CONDENA/DESCON RED ACE INOX 30MM', 1.0, 6.87, 6.87, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (50, 1, 'herraje', 'BIS SEGUR INOX 150X82MM MOD 565', 3.0, 10.01, 30.03, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (51, 1, 'herraje', 'P SPRAY ELECTRODOMESTICO 400ML BCO', 1.0, 8.4, 8.4, '2026-06-28 17:20:48', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (52, 1, 'herraje', 'CONDENA DESBLOQUEO RED LAT CR SAT', 1.0, 12.84, 12.84, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (53, 1, 'herraje', 'TIRADOR METAL CR MT P-544.128', 2.0, 3.59, 7.18, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (54, 1, 'herraje', 'CONDENA/DESCON RED ACE INOX 30MM', 1.0, 6.87, 6.87, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (55, 1, 'herraje', 'BIS SEGUR INOX 150X82MM MOD 565', 3.0, 10.01, 30.03, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (56, 1, 'herraje', 'P SPRAY ELECTRODOMESTICO 400ML BCO', 1.0, 8.4, 8.4, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (57, 1, 'herraje', 'CONDENA DESBLOQUEO RED LAT CR SAT', 1.0, 12.84, 12.84, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (58, 1, 'herraje', 'TIRADOR METAL CR MT P-544.128', 2.0, 3.59, 7.18, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (59, 1, 'herraje', 'CONDENA/DESCON RED ACE INOX 30MM', 1.0, 6.87, 6.87, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (60, 1, 'herraje', 'BIS SEGUR INOX 150X82MM MOD 565', 3.0, 10.01, 30.03, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (61, 1, 'herraje', 'P SPRAY ELECTRODOMESTICO 400ML BCO', 1.0, 8.4, 8.4, '2026-06-28 17:21:57', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (62, 14, 'presupuesto', 'Poner rodapié', 1.0, 200.0, 200.0, '2026-06-28 17:22:54', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (63, 10, 'presupuesto', 'Montaje', 1.0, 200.0, 200.0, '2026-06-28 17:26:02', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (69, 15, 'presupuesto', 'Instalación rodapié', 1.0, 250.0, 250.0, '2026-07-01 21:16:52', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (72, 5, 'presupuesto', 'Tapajuntas y otros', 1.0, 450.0, 450.0, '2026-07-01 21:46:39', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (74, 3, 'presupuesto', 'Mueble Registro', 1.0, 370.0, 370.0, '2026-07-01 21:57:14', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (76, 8, 'otro', 'Rodapie', 1.0, 10.0, 10.0, '2026-07-04 17:26:56', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (77, 15, 'herraje', 'Polimero', 2.0, 8.0, 16.0, '2026-07-04 17:37:39', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (78, 15, 'herraje', 'Cianoclirato', 1.0, 10.0, 10.0, '2026-07-04 17:38:15', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (79, 15, 'herraje', 'Acrilica blanco', 2.0, 1.8, 3.6, '2026-07-04 17:39:05', '');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (80, 15, 'herraje', 'Madera', 1.0, 3.5, 3.5, '2026-07-04 22:39:35', 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000802_Marta_Oscar\\tickets\\ocr_test.png');
INSERT IGNORE INTO `gastos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`, `ticket_foto`) VALUES (81, 15, 'herraje', 'Tornillos', 1.0, 8.84, 8.84, '2026-07-04 22:39:35', 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000802_Marta_Oscar\\tickets\\ocr_test.png');

-- presupuestos_faena (8 filas)
INSERT IGNORE INTO `presupuestos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`) VALUES (3, 15, 'mano_obra', 'Instalacion rodapie', 1.0, 200.0, 200.0, '2026-07-04 17:36:38');
INSERT IGNORE INTO `presupuestos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`) VALUES (4, 15, 'material', 'Adhesivo', 1.0, 50.0, 50.0, '2026-07-04 17:37:05');
INSERT IGNORE INTO `presupuestos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`) VALUES (7, 6, 'mano_obra', 'Instalacion rodapie', 1.0, 400.0, 400.0, '2026-07-04 17:51:47');
INSERT IGNORE INTO `presupuestos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`) VALUES (8, 6, 'mano_obra', 'Montaje puertas', 7.0, 70.0, 490.0, '2026-07-04 17:52:23');
INSERT IGNORE INTO `presupuestos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`) VALUES (9, 3, 'otro', 'Mueble registro', 1.0, 370.0, 370.0, '2026-07-04 17:53:31');
INSERT IGNORE INTO `presupuestos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`) VALUES (10, 7, 'otro', 'Puertas registro', 1.0, 90.0, 90.0, '2026-07-04 18:08:39');
INSERT IGNORE INTO `presupuestos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`) VALUES (11, 5, 'material', 'Melamina blanco 30 244 122 3m cuadrados', 1.0, 450.0, 450.0, '2026-07-04 19:19:56');
INSERT IGNORE INTO `presupuestos_faena` (`id`, `faena_id`, `tipo`, `descripcion`, `cantidad`, `precio_unitario`, `total`, `fecha`) VALUES (12, 2, 'Mobiliario', 'Cocina', 1.0, 5200.0, 5200.0, '2026-07-04 20:06:59');

-- fotos_faena (0 filas)

-- book_fotos (1 filas)
INSERT IGNORE INTO `book_fotos` (`id`, `faena_id`, `ruta_foto`, `titulo`, `descripcion`, `fecha`, `orden`) VALUES (3, 3, 'C:\\Users\\Ser3gix\\Desktop\\faenas-app\\datos\\000301_Amparo_hna_vte_rodrigo\\fotos\\foto_1779221283032_1.jpg', '', '', '2026-05-30 16:17:57', 3);
