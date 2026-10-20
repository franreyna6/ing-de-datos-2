/// Hito 9 - Componente embebido de una Sede (composicion).
/// Extiende %SerialObject: no tiene identidad propia, no existe fuera de su Sede
/// y se guarda junto con ella en el mismo %Save(). En SQL se proyecta como
/// columnas de la tabla Fixture.Sede (Ubicacion_Ciudad, Ubicacion_Pais).
Class Fixture.Direccion Extends %SerialObject
{

Property Ciudad As %String(MAXLEN = 80) [ Required ];

Property Pais As %String(MAXLEN = 60) [ Required ];

}
