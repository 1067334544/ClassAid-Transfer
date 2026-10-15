// SAMPLE TASK - NOT REVIEWED BY AN INSTRUCTOR.  For verifying the ClassAid workflow only.

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class IntLinkedListTest {
    private static IntLinkedList listOf(int... values) {
        IntLinkedList list = new IntLinkedList();
        for (int v : values) {
            list.add(v);
        }
        return list;
    }

    @Test
    void removeFromEmptyList() {
        IntLinkedList list = listOf();
        assertFalse(list.remove(1), "remove() on an empty list should return false");
        assertEquals("[]", list.toString());
    }

    @Test
    void removeMissingValue() {
        IntLinkedList list = listOf(1, 2, 3);
        assertFalse(list.remove(9), "remove() of a value not in the list should return false");
        assertEquals("[1, 2, 3]", list.toString());
    }

    @Test
    void removeHead() {
        IntLinkedList list = listOf(1, 2, 3);
        assertTrue(list.remove(1));
        assertEquals("[2, 3]", list.toString());
    }

    @Test
    void removeMiddle() {
        IntLinkedList list = listOf(1, 2, 3);
        assertTrue(list.remove(2));
        assertEquals("[1, 3]", list.toString());
    }

    @Test
    void removeTail() {
        IntLinkedList list = listOf(1, 2, 3);
        assertTrue(list.remove(3));
        assertEquals("[1, 2]", list.toString());
    }

    @Test
    void removeOnlyElement() {
        IntLinkedList list = listOf(4);
        assertTrue(list.remove(4));
        assertEquals("[]", list.toString());
        list.add(5);
        assertEquals("[5]", list.toString(), "the list should still work after becoming empty");
    }

    @Test
    void removesOnlyFirstOccurrence() {
        IntLinkedList list = listOf(2, 7, 2);
        assertTrue(list.remove(2));
        assertEquals("[7, 2]", list.toString());
    }

    @Test
    void sizeUpdates() {
        IntLinkedList list = listOf(1, 2, 3);
        list.remove(2);
        assertEquals(2, list.size());
        list.remove(9);
        assertEquals(2, list.size(), "size must not change when nothing is removed");
    }
}
