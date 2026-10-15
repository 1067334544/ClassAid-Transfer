// SAMPLE TASK - NOT REVIEWED BY AN INSTRUCTOR.  For verifying the ClassAid workflow only.

/** A singly linked list of ints. */
public class IntLinkedList {
    static class Node {
        int value;
        Node next;

        Node(int value) {
            this.value = value;
        }
    }

    private Node head;
    private int size;

    /** Appends a value to the end of the list. */
    public void add(int value) {
        Node node = new Node(value);
        if (head == null) {
            head = node;
        } else {
            Node cur = head;
            while (cur.next != null) {
                cur = cur.next;
            }
            cur.next = node;
        }
        size++;
    }

    /** Number of values in the list. */
    public int size() {
        return size;
    }

    /**
     * Removes the first node holding {@code value}.
     * Returns true if a node was removed, false if the value is not in the list.
     */
    public boolean remove(int value) {
        // TODO: implement
        return false;
    }

    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder("[");
        for (Node cur = head; cur != null; cur = cur.next) {
            sb.append(cur.value);
            if (cur.next != null) {
                sb.append(", ");
            }
        }
        return sb.append("]").toString();
    }
}
