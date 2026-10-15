// SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
//
// SPDX-License-Identifier: AGPL-3.0-only

import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeoutException;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

import org.junit.platform.engine.TestExecutionResult;
import org.junit.platform.engine.TestSource;
import org.junit.platform.engine.discovery.DiscoverySelectors;
import org.junit.platform.engine.support.descriptor.MethodSource;
import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.TestExecutionListener;
import org.junit.platform.launcher.TestIdentifier;
import org.junit.platform.launcher.TestPlan;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;

/**
 * ClassAid code-execution harness.
 *
 * Runs inside the (local or containerized) JVM that executes student code, so that
 * every runner produces structured results from the same code.
 *
 * Input: one JSON object on stdin:
 *   {"mode": "run"|"tests", "files": {name: source}, "tests": {name: source},
 *    "entry": "Main", "time_limit_ms": 5000, "test_timeout_ms": 2000,
 *    "max_frames": 20, "result_path": "/work/result-NONCE.json"}
 * Sources are compiled in memory and never written to disk, so student code cannot
 * read instructor test sources from the file system.
 *
 * Output: one JSON object written (atomically) to result_path.  The student program's
 * own stdout/stderr pass through unchanged to the process's stdout/stderr.
 */
public final class ClassAidHarness {

    private static final Object EMIT_LOCK = new Object();
    private static boolean emitted = false;
    private static Path resultPath;
    private static final long START = System.nanoTime();

    // Shared state that may be emitted early (timeout, System.exit via shutdown hook)
    private static final Map<String, Object> RESULT = new LinkedHashMap<>();
    private static final Map<String, Map<String, Object>> TESTS = new LinkedHashMap<>();

    private ClassAidHarness() {}

    public static void main(String[] args) throws Exception {
        // Diagnostics and exception messages must not depend on the host's locale.
        Locale.setDefault(Locale.ENGLISH);
        Map<String, Object> input = asMap(new JsonParser(readAll(System.in)).parse());
        resultPath = Path.of((String) input.get("result_path"));
        String mode = (String) input.get("mode");
        Map<String, Object> files = asMap(input.get("files"));
        Map<String, Object> tests = input.containsKey("tests") ? asMap(input.get("tests")) : Map.of();
        long timeLimit = ((Number) input.get("time_limit_ms")).longValue();
        int maxFrames = ((Number) input.getOrDefault("max_frames", 20)).intValue();

        RESULT.put("mode", mode);
        RESULT.put("status", "internal_error");
        RESULT.put("exception", null);
        RESULT.put("tests", null);

        // If student code calls System.exit(), the JVM runs shutdown hooks: report what we have.
        Runtime.getRuntime().addShutdownHook(new Thread(() -> emit("exited")));

        Path outDir = Files.createTempDirectory("classaid-classes");
        Map<String, Object> compile = compile(files, "tests".equals(mode) ? tests : Map.of(), outDir);
        RESULT.put("compile", compile);
        if (!Boolean.TRUE.equals(compile.get("ok"))) {
            emitAndHalt("compile_error", 0);
        }

        Set<String> studentFiles = files.keySet();
        URLClassLoader loader = new URLClassLoader(new URL[] {outDir.toUri().toURL()}, ClassAidHarness.class.getClassLoader());

        if ("run".equals(mode)) {
            runMain(loader, (String) input.get("entry"), timeLimit, studentFiles, maxFrames);
        } else {
            long testTimeout = ((Number) input.getOrDefault("test_timeout_ms", 2000)).longValue();
            runTests(loader, tests.keySet(), timeLimit, testTimeout, studentFiles, maxFrames);
        }
    }

    // ---------------------------------------------------------------- compile

    private static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String name, String code) {
            super(URI.create("string:///" + name), JavaFileObject.Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static Map<String, Object> compile(Map<String, Object> files, Map<String, Object> tests, Path outDir) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        DiagnosticCollector<JavaFileObject> collector = new DiagnosticCollector<>();
        List<JavaFileObject> sources = new ArrayList<>();
        for (Map.Entry<String, Object> e : files.entrySet()) {
            sources.add(new StringSource(e.getKey(), (String) e.getValue()));
        }
        for (Map.Entry<String, Object> e : tests.entrySet()) {
            sources.add(new StringSource(e.getKey(), (String) e.getValue()));
        }
        boolean ok;
        try (StandardJavaFileManager fm = compiler.getStandardFileManager(collector, Locale.ENGLISH, StandardCharsets.UTF_8)) {
            fm.setLocation(StandardLocation.CLASS_OUTPUT, List.of(outDir.toFile()));
            List<String> options = List.of("-encoding", "UTF-8", "-g", "-proc:none", "-Xlint:none",
                                           "-classpath", System.getProperty("java.class.path"));
            ok = compiler.getTask(null, fm, collector, options, null, sources).call();
        }

        List<Object> diagnostics = new ArrayList<>();
        for (Diagnostic<? extends JavaFileObject> d : collector.getDiagnostics()) {
            if (d.getKind() == Diagnostic.Kind.NOTE || d.getKind() == Diagnostic.Kind.OTHER) {
                continue;
            }
            String name = d.getSource() == null ? null : d.getSource().getName().replaceFirst("^/", "");
            boolean inTests = name != null && tests.containsKey(name);
            Map<String, Object> diag = new LinkedHashMap<>();
            diag.put("kind", d.getKind() == Diagnostic.Kind.ERROR ? "error" : "warning");
            // Do not reveal instructor test file names or positions.
            diag.put("file", inTests ? null : name);
            diag.put("line", inTests || d.getLineNumber() == Diagnostic.NOPOS ? null : d.getLineNumber());
            diag.put("column", inTests || d.getColumnNumber() == Diagnostic.NOPOS ? null : d.getColumnNumber());
            diag.put("in_tests", inTests);
            diag.put("message", d.getMessage(Locale.ENGLISH));
            diagnostics.add(diag);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ok", ok);
        result.put("diagnostics", diagnostics);
        return result;
    }

    // ---------------------------------------------------------------- run mode

    private static void runMain(URLClassLoader loader, String entry, long timeLimit, Set<String> studentFiles, int maxFrames) throws Exception {
        final Throwable[] failure = new Throwable[1];
        Method main;
        try {
            main = Class.forName(entry, true, loader).getMethod("main", String[].class);
        } catch (ClassNotFoundException | NoSuchMethodException | ExceptionInInitializerError e) {
            RESULT.put("exception", describe(e instanceof ExceptionInInitializerError && e.getCause() != null ? e.getCause() : e, studentFiles, maxFrames));
            emitAndHalt("runtime_error", 1);
            return;
        }
        // Large explicit stack so deep-but-finite recursion works; infinite recursion still overflows.
        Thread t = new Thread(null, () -> {
            try {
                main.invoke(null, (Object) new String[0]);
            } catch (InvocationTargetException e) {
                failure[0] = e.getCause();
            } catch (Throwable e) {  // NOPMD - report anything the student program triggers
                failure[0] = e;
            }
        }, "classaid-main", 64L * 1024 * 1024);
        t.setContextClassLoader(loader);
        t.start();
        t.join(timeLimit);
        System.out.flush();
        System.err.flush();
        if (t.isAlive()) {
            emitAndHalt("timeout", 124);
        } else if (failure[0] != null) {
            RESULT.put("exception", describe(failure[0], studentFiles, maxFrames));
            emitAndHalt("runtime_error", 1);
        } else {
            emitAndHalt("ok", 0);
        }
    }

    // ---------------------------------------------------------------- tests mode

    private static void runTests(URLClassLoader loader, Set<String> testFiles, long timeLimit, long testTimeout,
                                 Set<String> studentFiles, int maxFrames) throws Exception {
        LauncherDiscoveryRequestBuilder builder = LauncherDiscoveryRequestBuilder.request()
            .configurationParameter("junit.jupiter.execution.timeout.default", testTimeout + " ms")
            .configurationParameter("junit.jupiter.execution.timeout.thread.mode.default", "SEPARATE_THREAD");
        Thread.currentThread().setContextClassLoader(loader);
        for (String file : testFiles) {
            String className = file.replaceFirst("\\.java$", "");
            builder.selectors(DiscoverySelectors.selectClass(Class.forName(className, false, loader)));
        }
        LauncherDiscoveryRequest request = builder.build();
        Launcher launcher = LauncherFactory.create();
        TestPlan plan = launcher.discover(request);

        // Every discovered test starts as "not_run"; the listener fills in results.
        synchronized (EMIT_LOCK) {
            for (TestIdentifier root : plan.getRoots()) {
                for (TestIdentifier id : plan.getDescendants(root)) {
                    if (id.isTest()) {
                        Map<String, Object> entry = new LinkedHashMap<>();
                        String[] cm = classAndMethod(id.getSource().orElse(null));
                        entry.put("id", cm[0] + "#" + cm[1]);
                        entry.put("class", cm[0]);
                        entry.put("method", cm[1]);
                        entry.put("name", id.getDisplayName());
                        entry.put("status", "not_run");
                        entry.put("message", null);
                        entry.put("exception", null);
                        TESTS.put(id.getUniqueId(), entry);
                    }
                }
            }
        }

        TestExecutionListener listener = new TestExecutionListener() {
            @Override
            public void executionSkipped(TestIdentifier id, String reason) {
                synchronized (EMIT_LOCK) {
                    Map<String, Object> e = TESTS.get(id.getUniqueId());
                    if (e != null) {
                        e.put("status", "skipped");
                        e.put("message", reason);
                    }
                }
            }

            @Override
            public void executionFinished(TestIdentifier id, TestExecutionResult r) {
                synchronized (EMIT_LOCK) {
                    Throwable thrown = r.getThrowable().orElse(null);
                    if (!id.isTest()) {
                        // A container failed (e.g., class init or @BeforeAll): fail its unfinished tests.
                        if (r.getStatus() == TestExecutionResult.Status.FAILED) {
                            for (Map.Entry<String, Map<String, Object>> e : TESTS.entrySet()) {
                                if (e.getKey().startsWith(id.getUniqueId()) && "not_run".equals(e.getValue().get("status"))) {
                                    fillFailure(e.getValue(), "error", thrown, studentFiles, maxFrames);
                                }
                            }
                        }
                        return;
                    }
                    Map<String, Object> e = TESTS.get(id.getUniqueId());
                    if (e == null) {
                        return;
                    }
                    switch (r.getStatus()) {
                        case SUCCESSFUL -> e.put("status", "passed");
                        case ABORTED -> {
                            e.put("status", "skipped");
                            e.put("message", thrown == null ? null : truncate(thrown.getMessage(), 1000));
                        }
                        case FAILED -> {
                            String status = thrown instanceof AssertionError ? "failed"
                                : thrown instanceof TimeoutException ? "timeout" : "error";
                            fillFailure(e, status, thrown, studentFiles, maxFrames);
                        }
                    }
                }
            }
        };

        Thread t = new Thread(null, () -> launcher.execute(request, listener), "classaid-tests", 64L * 1024 * 1024);
        t.setContextClassLoader(loader);
        t.start();
        t.join(timeLimit);
        System.out.flush();
        System.err.flush();
        emitAndHalt(t.isAlive() ? "timeout" : "ok", t.isAlive() ? 124 : 0);
    }

    private static void fillFailure(Map<String, Object> e, String status, Throwable thrown, Set<String> studentFiles, int maxFrames) {
        e.put("status", status);
        if (thrown != null) {
            e.put("message", truncate(thrown.getMessage(), 1000));
            if (!"failed".equals(status)) {
                e.put("exception", describe(thrown, studentFiles, maxFrames));
            }
        }
    }

    private static String[] classAndMethod(TestSource source) {
        if (source instanceof MethodSource ms) {
            return new String[] {ms.getClassName(), ms.getMethodName()};
        }
        return new String[] {"?", "?"};
    }

    // ---------------------------------------------------------------- results

    private static Map<String, Object> describe(Throwable t, Set<String> studentFiles, int maxFrames) {
        Map<String, Object> ex = new LinkedHashMap<>();
        ex.put("type", t.getClass().getName());
        ex.put("message", truncate(t.getMessage(), 1000));
        List<Object> frames = new ArrayList<>();
        for (StackTraceElement el : t.getStackTrace()) {
            if (frames.size() >= maxFrames) {
                break;
            }
            if (el.getFileName() != null && studentFiles.contains(el.getFileName())) {
                Map<String, Object> f = new LinkedHashMap<>();
                f.put("file", el.getFileName());
                f.put("line", el.getLineNumber());
                f.put("class", el.getClassName());
                f.put("method", el.getMethodName());
                frames.add(f);
            }
        }
        ex.put("frames", frames);
        return ex;
    }

    private static void emit(String status) {
        synchronized (EMIT_LOCK) {
            if (emitted) {
                return;
            }
            emitted = true;
            RESULT.put("status", status);
            if (!TESTS.isEmpty()) {
                List<Object> tests = new ArrayList<>(TESTS.values());
                if (!"ok".equals(status)) {
                    // Tests that never finished because the run was cut short.
                    for (Object o : tests) {
                        @SuppressWarnings("unchecked")
                        Map<String, Object> e = (Map<String, Object>) o;
                        if ("not_run".equals(e.get("status"))) {
                            e.put("status", "timeout".equals(status) ? "timeout" : "error");
                        }
                    }
                }
                RESULT.put("tests", tests);
            }
            RESULT.put("harness_ms", (System.nanoTime() - START) / 1_000_000);
            try {
                Path tmp = resultPath.resolveSibling(resultPath.getFileName() + ".tmp");
                Files.writeString(tmp, Json.write(RESULT), StandardCharsets.UTF_8);
                Files.move(tmp, resultPath, StandardCopyOption.ATOMIC_MOVE);
            } catch (Throwable e) {  // NOPMD - nothing more we can do; the runner reports a missing result
                System.err.println("ClassAidHarness: failed to write result: " + e);
            }
        }
    }

    private static void emitAndHalt(String status, int code) {
        emit(status);
        System.out.flush();
        System.err.flush();
        Runtime.getRuntime().halt(code);
    }

    private static String truncate(String s, int max) {
        if (s == null || s.length() <= max) {
            return s;
        }
        return s.substring(0, max) + "...";
    }

    private static String readAll(InputStream in) throws Exception {
        return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object o) {
        return (Map<String, Object>) o;
    }

    // ---------------------------------------------------------------- minimal JSON

    /** Minimal JSON writer for the result structure (maps, lists, strings, numbers, booleans, null). */
    static final class Json {
        private Json() {}

        static String write(Object o) {
            StringBuilder sb = new StringBuilder();
            write(sb, o);
            return sb.toString();
        }

        private static void write(StringBuilder sb, Object o) {
            if (o == null) {
                sb.append("null");
            } else if (o instanceof String s) {
                str(sb, s);
            } else if (o instanceof Number || o instanceof Boolean) {
                sb.append(o);
            } else if (o instanceof Map<?, ?> m) {
                sb.append('{');
                boolean first = true;
                for (Map.Entry<?, ?> e : m.entrySet()) {
                    if (!first) {
                        sb.append(',');
                    }
                    first = false;
                    str(sb, String.valueOf(e.getKey()));
                    sb.append(':');
                    write(sb, e.getValue());
                }
                sb.append('}');
            } else if (o instanceof List<?> l) {
                sb.append('[');
                for (int i = 0; i < l.size(); i++) {
                    if (i > 0) {
                        sb.append(',');
                    }
                    write(sb, l.get(i));
                }
                sb.append(']');
            } else {
                str(sb, String.valueOf(o));
            }
        }

        private static void str(StringBuilder sb, String s) {
            sb.append('"');
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                switch (c) {
                    case '"' -> sb.append("\\\"");
                    case '\\' -> sb.append("\\\\");
                    case '\n' -> sb.append("\\n");
                    case '\r' -> sb.append("\\r");
                    case '\t' -> sb.append("\\t");
                    default -> {
                        if (c < 0x20) {
                            sb.append(String.format("\\u%04x", (int) c));
                        } else {
                            sb.append(c);
                        }
                    }
                }
            }
            sb.append('"');
        }
    }

    /** Minimal JSON parser for the harness input (trusted: produced by the runner). */
    static final class JsonParser {
        private final String s;
        private int i = 0;

        JsonParser(String s) {
            this.s = s;
        }

        Object parse() {
            ws();
            Object v = value();
            ws();
            return v;
        }

        private Object value() {
            ws();
            char c = s.charAt(i);
            switch (c) {
                case '{': return object();
                case '[': return array();
                case '"': return string();
                case 't': i += 4; return Boolean.TRUE;
                case 'f': i += 5; return Boolean.FALSE;
                case 'n': i += 4; return null;
                default: return number();
            }
        }

        private Map<String, Object> object() {
            Map<String, Object> m = new LinkedHashMap<>();
            i++;
            ws();
            if (s.charAt(i) == '}') {
                i++;
                return m;
            }
            while (true) {
                ws();
                String k = string();
                ws();
                i++;  // ':'
                m.put(k, value());
                ws();
                char c = s.charAt(i++);
                if (c == '}') {
                    return m;
                }
            }
        }

        private List<Object> array() {
            List<Object> l = new ArrayList<>();
            i++;
            ws();
            if (s.charAt(i) == ']') {
                i++;
                return l;
            }
            while (true) {
                l.add(value());
                ws();
                char c = s.charAt(i++);
                if (c == ']') {
                    return l;
                }
            }
        }

        private String string() {
            StringBuilder sb = new StringBuilder();
            i++;  // opening quote
            while (true) {
                char c = s.charAt(i++);
                if (c == '"') {
                    return sb.toString();
                }
                if (c == '\\') {
                    char e = s.charAt(i++);
                    switch (e) {
                        case 'n' -> sb.append('\n');
                        case 'r' -> sb.append('\r');
                        case 't' -> sb.append('\t');
                        case 'b' -> sb.append('\b');
                        case 'f' -> sb.append('\f');
                        case 'u' -> {
                            sb.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                            i += 4;
                        }
                        default -> sb.append(e);  // \" \\ \/
                    }
                } else {
                    sb.append(c);
                }
            }
        }

        private Number number() {
            int start = i;
            while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) {
                i++;
            }
            String n = s.substring(start, i);
            if (n.contains(".") || n.contains("e") || n.contains("E")) {
                return Double.parseDouble(n);
            }
            return Long.parseLong(n);
        }

        private void ws() {
            while (i < s.length() && Character.isWhitespace(s.charAt(i))) {
                i++;
            }
        }
    }
}
