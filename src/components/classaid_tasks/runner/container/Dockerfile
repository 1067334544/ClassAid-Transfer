# syntax=docker/dockerfile:1.6
# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

# Image for ClassAid's DockerRunner.  Build from src/components/classaid_tasks/runner/:
#
#   docker build -t classaid-runner:junit-1.14.4 -f container/Dockerfile .
#
# The tag must match DEFAULT_IMAGE in docker.py (or set CLASSAID_DOCKER_IMAGE).

FROM eclipse-temurin:21-jdk

# Pinned JUnit standalone jar; keep version and checksum in sync with deps.py.
ADD --checksum=sha256:7c6968cbcaf4301c729f202b23b7d736c5d88be625fc7d27ad5d746146a8bc28 \
    https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/1.14.4/junit-platform-console-standalone-1.14.4.jar \
    /opt/classaid/junit.jar

COPY java/ClassAidHarness.java /opt/classaid/src/ClassAidHarness.java
RUN mkdir -p /opt/classaid/harness \
 && javac -encoding UTF-8 -cp /opt/classaid/junit.jar -d /opt/classaid/harness /opt/classaid/src/ClassAidHarness.java \
 && rm -rf /opt/classaid/src \
 && chmod -R a+rX /opt/classaid

USER 65534:65534
WORKDIR /work
