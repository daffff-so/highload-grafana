FROM maven:3.9.11-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B verify

FROM eclipse-temurin:17.0.17_10-jdk-jammy
RUN groupadd --system app && useradd --system --gid app app
WORKDIR /app
COPY --from=build --chown=app:app /build/target/highload-grafana-0.0.1-SNAPSHOT.jar app.jar
COPY --chown=app:app docker/Healthcheck.java /app/Healthcheck.java
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
