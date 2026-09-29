-- INIS — initialisation PostgreSQL au premier démarrage du conteneur (§16.1).
--
-- Ce script ne crée *aucune* table : le schéma §27 appartient exclusivement à
-- Alembic (`alembic upgrade head`, §41.14). Il se limite aux extensions que les
-- migrations 0001/0003 supposent disponibles, afin qu'une base fraîchement
-- provisionnée puisse les créer sans privilège superutilisateur.

-- uuid-ossp / pgcrypto : identifiants et hachage (migration 0001).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- vector : recherche sémantique pgvector + index HNSW (§16.1, migration 0003).
CREATE EXTENSION IF NOT EXISTS "vector";

-- pg_trgm : recherche floue lexicale (utilisée comme repli des requêtes §16.2).
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Garde-fou : la recherche lexique §16.2 s'appuie sur `to_tsvector` sans
-- configuration explicite ; elle doit donc rester alignée sur le défaut du
-- serveur, sinon requête et index utilisent des lexèmes différents.
DO $$
BEGIN
    EXECUTE format(
        'ALTER DATABASE %I SET default_text_search_config = %L',
        current_database(),
        'pg_catalog.english'
    );
END
$$;

